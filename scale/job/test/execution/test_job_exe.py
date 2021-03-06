from __future__ import unicode_literals

from datetime import timedelta

import django
from django.test import TestCase
from django.utils.timezone import now

import job.test.utils as job_test_utils
from error.models import Error, CACHED_BUILTIN_ERRORS
from job.execution.job_exe import RunningJobExecution
from job.models import JobExecution
from job.tasks.base_task import RUNNING_RECON_THRESHOLD
from job.tasks.manager import TaskManager
from job.tasks.update import TaskStatusUpdate
from scheduler.models import Scheduler


class TestRunningJobExecution(TestCase):
    """Tests the RunningJobExecution class"""

    fixtures = ['basic_errors.json', 'basic_job_errors.json']

    def setUp(self):
        django.setup()

        Scheduler.objects.initialize_scheduler()
        job_type = job_test_utils.create_job_type(max_tries=1)
        job = job_test_utils.create_job(job_type=job_type, num_exes=1)
        job_exe = job_test_utils.create_job_exe(job=job, status='RUNNING')
        self._job_exe_id = job_exe.id

        self.agent_id = 'agent'

        self.task_mgr = TaskManager()

    def test_successful_normal_job_execution(self):
        """Tests running through a normal job execution successfully"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)
        self.assertFalse(running_job_exe.is_finished())
        self.assertTrue(running_job_exe.is_next_task_ready())

        # Start pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_id = task.id
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Pull-task running
        pull_task_started = now() - timedelta(minutes=5)  # Lots of time so now() called at completion is in future
        update = job_test_utils.create_task_status_update(pull_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Complete pull-task
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pull_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertTrue(running_job_exe.is_next_task_ready())

        # Start pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_id = task.id
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Pre-task running
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Pre-task sets updated command arguments
        updated_commands_args = '-arg updated'
        JobExecution.objects.filter(id=self._job_exe_id).update(command_arguments=updated_commands_args)

        # Complete pre-task
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed, exit_code=1)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertTrue(running_job_exe.is_next_task_ready())

        # Start job-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        job_task_id = task.id
        self.assertEqual(task._command_arguments, updated_commands_args)  # Make sure job task has updated command args
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Job-task running
        job_task_started = pre_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(job_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          job_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Complete job-task
        job_task_completed = job_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(job_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          job_task_completed, exit_code=2)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertTrue(running_job_exe.is_next_task_ready())

        # Start post-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        post_task_id = task.id
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Post-task running
        post_task_started = job_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(post_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          post_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Complete post-task
        post_task_completed = post_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(post_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          post_task_completed, exit_code=3)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'COMPLETED')
        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=self._job_exe_id)
        self.assertEqual(pre_task_started, job_exe.pre_started)
        self.assertEqual(pre_task_completed, job_exe.pre_completed)
        self.assertEqual(1, job_exe.pre_exit_code)
        self.assertEqual(job_task_started, job_exe.job_started)
        self.assertEqual(job_task_completed, job_exe.job_completed)
        self.assertEqual(2, job_exe.job_exit_code)
        self.assertEqual(post_task_started, job_exe.post_started)
        self.assertEqual(post_task_completed, job_exe.post_completed)
        self.assertEqual(3, job_exe.post_exit_code)
        self.assertEqual('COMPLETED', job_exe.status)
        self.assertGreater(job_exe.ended, post_task_completed)

    def test_failed_normal_job_execution(self):
        """Tests running through a normal job execution that fails"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)
        self.assertFalse(running_job_exe.is_finished())
        self.assertTrue(running_job_exe.is_next_task_ready())

        # Start pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_id = task.id
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Pull-task running
        pull_task_started = now() - timedelta(minutes=5)  # Lots of time so now() called at completion is in future
        update = job_test_utils.create_task_status_update(pull_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Complete pull-task
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pull_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertTrue(running_job_exe.is_next_task_ready())

        # Start pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_id = task.id
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Pre-task running
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(running_job_exe.is_finished())
        self.assertFalse(running_job_exe.is_next_task_ready())

        # Fail pre-task
        pre_task_failed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.FAILED,
                                                          pre_task_failed, exit_code=1)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'FAILED')
        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=self._job_exe_id)
        self.assertEqual(pre_task_started, job_exe.pre_started)
        self.assertEqual(pre_task_failed, job_exe.pre_completed)
        self.assertEqual(1, job_exe.pre_exit_code)
        self.assertEqual('FAILED', job_exe.status)
        self.assertIsNotNone(job_exe.error_id)
        self.assertGreater(job_exe.ended, pre_task_failed)

    def test_timed_out_launch(self):
        """Tests running through a job execution where a task launch times out"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start, run, and complete pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Launch job-task and then times out
        when_launched = pre_task_completed + timedelta(seconds=1)
        when_timed_out = when_launched + timedelta(seconds=1)
        job_task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([job_task], when_launched)
        running_job_exe.execution_timed_out(job_task, when_timed_out)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'FAILED')
        self.assertEqual(running_job_exe.error_category, 'SYSTEM')

        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=self._job_exe_id)
        self.assertEqual('FAILED', job_exe.status)
        self.assertEqual('launch-timeout', job_exe.error.name)
        self.assertEqual(when_timed_out, job_exe.ended)

    def test_timed_out_pull_task(self):
        """Tests running through a job execution where the pull task times out"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start pull-task and then task times out
        when_launched = now()
        pull_task_started = when_launched + timedelta(seconds=1)
        when_timed_out = pull_task_started + timedelta(seconds=1)
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], when_launched)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        running_job_exe.execution_timed_out(task, when_timed_out)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'FAILED')
        self.assertEqual(running_job_exe.error_category, 'SYSTEM')
        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=self._job_exe_id)
        self.assertEqual('FAILED', job_exe.status)
        self.assertEqual('pull-timeout', job_exe.error.name)
        self.assertEqual(when_timed_out, job_exe.ended)

    def test_timed_out_pre_task(self):
        """Tests running through a job execution where the pre task times out"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start pre-task and then task times out
        when_launched = pull_task_completed + timedelta(seconds=1)
        pre_task_started = when_launched + timedelta(seconds=1)
        when_timed_out = pre_task_started + timedelta(seconds=1)
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], when_launched)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        running_job_exe.execution_timed_out(task, when_timed_out)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'FAILED')
        self.assertEqual(running_job_exe.error_category, 'SYSTEM')
        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=self._job_exe_id)
        self.assertEqual('FAILED', job_exe.status)
        self.assertEqual('pre-timeout', job_exe.error.name)
        self.assertEqual(when_timed_out, job_exe.ended)

    def test_timed_out_job_task(self):
        """Tests running through a job execution where the job task times out"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start, run, and complete pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start job-task and then task times out
        when_launched = pre_task_completed + timedelta(seconds=1)
        job_task_started = when_launched + timedelta(seconds=1)
        when_timed_out = job_task_started + timedelta(seconds=1)
        job_task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([job_task], when_launched)
        update = job_test_utils.create_task_status_update(job_task.id, 'agent', TaskStatusUpdate.RUNNING,
                                                          job_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        running_job_exe.execution_timed_out(job_task, when_timed_out)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'FAILED')
        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=self._job_exe_id)
        self.assertEqual('FAILED', job_exe.status)
        self.assertEqual('timeout', job_exe.error.name)
        self.assertEqual(when_timed_out, job_exe.ended)

    def test_timed_out_system_job_task(self):
        """Tests running through a job execution where a system job task times out"""

        job_type = job_test_utils.create_job_type(max_tries=1)
        job_type.is_system = True
        job_type.save()
        job = job_test_utils.create_job(job_type=job_type, num_exes=1)
        job_exe = job_test_utils.create_job_exe(job=job)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start job-task and then task times out
        when_launched = now() + timedelta(seconds=1)
        job_task_started = when_launched + timedelta(seconds=1)
        when_timed_out = job_task_started + timedelta(seconds=1)
        job_task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([job_task], when_launched)
        update = job_test_utils.create_task_status_update(job_task.id, 'agent', TaskStatusUpdate.RUNNING,
                                                          job_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        running_job_exe.execution_timed_out(job_task, when_timed_out)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'FAILED')
        self.assertEqual(running_job_exe.error_category, 'SYSTEM')
        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=job_exe.id)
        self.assertEqual('FAILED', job_exe.status)
        self.assertEqual('system-timeout', job_exe.error.name)
        self.assertEqual(when_timed_out, job_exe.ended)

    def test_timed_out_post_task(self):
        """Tests running through a job execution where the post task times out"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start, run, and complete pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start, run, and complete job-task
        when_launched = pre_task_completed + timedelta(seconds=1)
        job_task_started = when_launched + timedelta(seconds=1)
        job_task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([job_task], when_launched)
        update = job_test_utils.create_task_status_update(job_task.id, 'agent', TaskStatusUpdate.RUNNING,
                                                          job_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        job_task_completed = job_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(job_task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          job_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start post-task and then task times out
        when_launched = job_task_completed + timedelta(seconds=1)
        post_task_started = when_launched + timedelta(seconds=1)
        when_timed_out = post_task_started + timedelta(seconds=1)
        post_task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([post_task], when_launched)
        update = job_test_utils.create_task_status_update(post_task.id, 'agent', TaskStatusUpdate.RUNNING,
                                                          post_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        running_job_exe.execution_timed_out(post_task, when_timed_out)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'FAILED')
        self.assertEqual(running_job_exe.error_category, 'SYSTEM')
        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=self._job_exe_id)
        self.assertEqual('FAILED', job_exe.status)
        self.assertEqual('post-timeout', job_exe.error.name)
        self.assertEqual(when_timed_out, job_exe.ended)

    def test_lost_job_execution(self):
        """Tests running through a job execution that gets lost"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start, run, and complete pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start job-task and then execution gets lost
        when_lost = pre_task_completed + timedelta(seconds=1)
        job_task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([job_task], now())
        running_job_exe.execution_lost(when_lost)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'FAILED')
        self.assertEqual(running_job_exe.error_category, 'SYSTEM')
        self.assertFalse(running_job_exe.is_next_task_ready())

        job_exe = JobExecution.objects.get(id=self._job_exe_id)
        self.assertEqual('FAILED', job_exe.status)
        self.assertEqual(Error.objects.get_builtin_error('node-lost').id, job_exe.error_id)
        self.assertEqual(when_lost, job_exe.ended)

    def test_lost_task(self):
        """Tests running through a job execution that has a task that gets lost"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start, run, and complete pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start job-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        job_task_id = task.id
        job_task_started = pre_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, job_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertTrue(task.has_started)

        # Lose task and make sure the "same" task is the next one to schedule again with a new ID this time
        when_lost = job_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(job_task_id, 'agent', TaskStatusUpdate.LOST, when_lost)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        self.assertFalse(task.has_started)
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        self.assertTrue(task.id.startswith(job_task_id))
        self.assertNotEqual(job_task_id, task.id)

    def test_canceled_job_execution(self):
        """Tests running through a job execution that gets canceled"""

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start, run, and complete pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start job-task and then execution gets canceled
        job_task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([job_task], now())
        canceled_task = running_job_exe.execution_canceled()
        self.assertEqual(job_task.id, canceled_task.id)
        self.assertTrue(running_job_exe.is_finished())
        self.assertEqual(running_job_exe.status, 'CANCELED')
        self.assertFalse(running_job_exe.is_next_task_ready())

    def test_pre_task_launch_error(self):
        """Tests running through a job execution where a pre-task fails to launch"""

        # Clear error cache so test works correctly
        CACHED_BUILTIN_ERRORS.clear()

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_id = task.id

        # Pre-task fails to launch
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.FAILED, now())
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Check results
        job_exe = JobExecution.objects.select_related().get(id=self._job_exe_id)
        self.assertEqual(job_exe.status, 'FAILED')
        self.assertEqual(job_exe.error.name, 'docker-task-launch')

    def test_job_task_launch_error(self):
        """Tests running through a job execution where a Docker-based job-task fails to launch"""

        # Clear error cache so test works correctly
        CACHED_BUILTIN_ERRORS.clear()

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_id = task.id

        # Pre-task running
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Complete pre-task
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start job-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        job_task_id = task.id

        # Job-task fails to launch
        update = job_test_utils.create_task_status_update(job_task_id, 'agent', TaskStatusUpdate.FAILED, now())
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Check results
        job_exe = JobExecution.objects.select_related().get(id=self._job_exe_id)
        self.assertEqual(job_exe.status, 'FAILED')
        self.assertEqual(job_exe.error.name, 'docker-task-launch')

    def test_post_task_launch_error(self):
        """Tests running through a job execution where a post-task fails to launch"""

        # Clear error cache so test works correctly
        CACHED_BUILTIN_ERRORS.clear()

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_id = task.id

        # Pre-task running
        pre_task_started = pull_task_completed + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Complete pre-task
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start job-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        job_task_id = task.id

        # Job-task running
        job_task_started = now()
        update = job_test_utils.create_task_status_update(job_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          job_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Complete job-task
        job_task_completed = job_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(job_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          job_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start post-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        post_task_id = task.id

        # Post-task fails to launch
        update = job_test_utils.create_task_status_update(post_task_id, 'agent', TaskStatusUpdate.FAILED, now())
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Check results
        job_exe = JobExecution.objects.select_related().get(id=self._job_exe_id)
        self.assertEqual(job_exe.status, 'FAILED')
        self.assertEqual(job_exe.error.name, 'docker-task-launch')

    def test_docker_pull_error(self):
        """Tests running through a job execution where the Docker image pull fails"""

        # Clear error cache so test works correctly
        CACHED_BUILTIN_ERRORS.clear()

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_id = task.id

        # Pull-task running
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(pull_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Pull-task fails
        update = job_test_utils.create_task_status_update(pull_task_id, 'agent', TaskStatusUpdate.FAILED, now())
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Check results
        job_exe = JobExecution.objects.select_related().get(id=self._job_exe_id)
        self.assertEqual(job_exe.status, 'FAILED')
        self.assertEqual(job_exe.error.name, 'pull')

    def test_general_algorithm_error(self):
        """Tests running through a job execution where the job-task has a general algorithm error (non-zero exit code)
        """

        # Clear error cache so test works correctly
        CACHED_BUILTIN_ERRORS.clear()

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_id = task.id

        # Pre-task running
        pre_task_started = now()
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Complete pre-task
        pre_task_completed = pre_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pre_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start job-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        job_task_id = task.id

        # Job-task running
        job_task_started = now()
        update = job_test_utils.create_task_status_update(job_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          job_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Fail job-task
        job_task_failed = job_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(job_task_id, 'agent', TaskStatusUpdate.FAILED,
                                                          job_task_failed, exit_code=1)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Check results
        job_exe = JobExecution.objects.select_related().get(id=self._job_exe_id)
        self.assertEqual(job_exe.status, 'FAILED')
        self.assertEqual(job_exe.error.name, 'algorithm-unknown')

    def test_docker_terminated_error(self):
        """Tests running through a job execution where a Docker container terminates"""

        # Clear error cache so test works correctly
        CACHED_BUILTIN_ERRORS.clear()

        job_exe = JobExecution.objects.get_job_exe_with_job_and_job_type(self._job_exe_id)
        running_job_exe = RunningJobExecution(self.agent_id, job_exe)

        # Start, run, and complete pull-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pull_task_started = now()
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.RUNNING, pull_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)
        pull_task_completed = pull_task_started + timedelta(seconds=1)
        update = job_test_utils.create_task_status_update(task.id, 'agent', TaskStatusUpdate.FINISHED,
                                                          pull_task_completed)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Start pre-task
        task = running_job_exe.start_next_task()
        self.task_mgr.launch_tasks([task], now())
        pre_task_id = task.id

        # Pre-task running
        pre_task_started = now()
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.RUNNING,
                                                          pre_task_started)
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Pre-task Docker container terminates
        update = job_test_utils.create_task_status_update(pre_task_id, 'agent', TaskStatusUpdate.FAILED, now(),
                                                          reason='REASON_EXECUTOR_TERMINATED')
        self.task_mgr.handle_task_update(update)
        running_job_exe.task_update(update)

        # Check results
        job_exe = JobExecution.objects.select_related().get(id=self._job_exe_id)
        self.assertEqual(job_exe.status, 'FAILED')
        self.assertEqual(job_exe.error.name, 'docker-terminated')

    def test_need_reconciliation(self):
        """Tests calling RunningJobExecution.need_reconciliation()"""

        job_exe_1 = job_test_utils.create_job_exe(status='RUNNING')
        job_exe_2 = job_test_utils.create_job_exe(status='RUNNING')
        job_exe_3 = job_test_utils.create_job_exe(status='RUNNING')
        job_exe_4 = job_test_utils.create_job_exe(status='RUNNING')

        running_job_exe_1 = RunningJobExecution(self.agent_id, job_exe_1)
        task_1 = running_job_exe_1.start_next_task()
        running_job_exe_2 = RunningJobExecution(self.agent_id, job_exe_2)
        task_2 = running_job_exe_2.start_next_task()
        running_job_exe_3 = RunningJobExecution(self.agent_id, job_exe_3)
        task_3 = running_job_exe_3.start_next_task()
        running_job_exe_4 = RunningJobExecution(self.agent_id, job_exe_4)
        task_4 = running_job_exe_4.start_next_task()

        task_1_and_2_launch_time = now()
        task_3_launch_time = task_1_and_2_launch_time + RUNNING_RECON_THRESHOLD
        check_time = task_3_launch_time + timedelta(seconds=1)

        # Task 1 and 2 launch
        task_1.launch(task_1_and_2_launch_time)
        task_2.launch(task_1_and_2_launch_time)

        # The reconciliation threshold has now expired
        # Task 3 launches and a task update comes for task 2
        task_3.launch(task_3_launch_time)
        update = job_test_utils.create_task_status_update(task_2.id, 'agent_id', TaskStatusUpdate.RUNNING,
                                                          task_3_launch_time)
        task_2.update(update)

        # A second later, we check for tasks needing reconciliation
        # Task 1 was launched a while ago (exceeding threshold) so it should be reconciled
        self.assertTrue(task_1.needs_reconciliation(check_time))
        # Task 2 received an update 1 second ago so it should not be reconciled
        self.assertFalse(task_2.needs_reconciliation(check_time))
        # Task 3 was launched 1 second ago so it should not be reconciled
        self.assertFalse(task_3.needs_reconciliation(check_time))
        # Task 4 did not even launch so it should not be reconciled
        self.assertFalse(task_4.needs_reconciliation(check_time))
