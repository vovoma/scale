"""Defines the class that manages system tasks"""
from __future__ import unicode_literals

import datetime
import logging
import threading

from django.utils.timezone import now

from job.tasks.update import TaskStatusUpdate
from scheduler.manager import scheduler_mgr
from scheduler.tasks.db_update_task import DatabaseUpdateTask


logger = logging.getLogger(__name__)


class SystemTaskManager(object):
    """This class manages all Scale system tasks. This class is thread-safe."""

    DATABASE_UPDATE_ERR_THRESHOLD = datetime.timedelta(minutes=2)

    def __init__(self):
        """Constructor
        """

        self._db_update_task = None
        self._is_db_update_completed = False
        self._last_db_update_task_failure = None
        self._when_db_update_completed = None

        self._lock = threading.Lock()

    def get_tasks_to_kill(self):
        """Returns a list of system tasks that need to be killed as soon as possible

        :returns: The list of system tasks to kill
        :rtype: list
        """

        return []

    def get_tasks_to_schedule(self, when):
        """Returns a list of system tasks that need to be scheduled as soon as possible

        :param when: The current time
        :type when: :class:`datetime.datetime`
        :returns: The list of system tasks to schedule
        :rtype: list
        """

        tasks = []

        with self._lock:
            # Create new database update task if needed
            if not self._db_update_task and not self._is_db_update_completed:
                threshold = SystemTaskManager.DATABASE_UPDATE_ERR_THRESHOLD
                if not self._last_db_update_task_failure or when - self._last_db_update_task_failure > threshold:
                    self._db_update_task = DatabaseUpdateTask(scheduler_mgr.framework_id)

            if self._db_update_task and not self._db_update_task.has_been_launched:
                tasks.append(self._db_update_task)

        return tasks

    def handle_task_update(self, task_update):
        """Handles the given task update

        :param task_update: The task update
        :type task_update: :class:`job.tasks.update.TaskStatusUpdate`
        """

        with self._lock:
            if self._db_update_task and self._db_update_task.id == task_update.task_id:
                self._last_db_update_task_failure = None

                if task_update.status == TaskStatusUpdate.FINISHED:
                    logger.info('Scale database update has completed')
                    self._is_db_update_completed = True
                    self._when_db_update_completed = now()
                elif task_update.status == TaskStatusUpdate.FAILED:
                    logger.warning('Scale database update has failed')
                    self._last_db_update_task_failure = now()
                elif task_update.status == TaskStatusUpdate.KILLED:
                    logger.warning('Scale database update was killed')
                elif task_update.status == TaskStatusUpdate.LOST:
                    logger.warning('Scale database update was lost')
                    self._db_update_task = None
                if self._db_update_task and self._db_update_task.has_ended:
                    self._db_update_task = None


system_task_mgr = SystemTaskManager()