"""Defines the JSON schema for describing the execution configuration"""
from __future__ import unicode_literals

import logging
import os

from jsonschema import validate
from jsonschema.exceptions import ValidationError

from job.configuration.exceptions import InvalidExecutionConfiguration
from job.configuration.json.execution import exe_config_1_1 as previous_version
from job.configuration.volume import MODE_RO, MODE_RW
from job.execution.container import SCALE_JOB_EXE_INPUT_PATH, SCALE_JOB_EXE_OUTPUT_PATH

logger = logging.getLogger(__name__)


SCHEMA_VERSION = '2.0'


EXE_CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'version': {
            'description': 'Version of the execution configuration schema',
            'type': 'string',
            'pattern': '^.{0,50}$',
        },
        'input_files': {
            'description': 'The input files and meta-data for this job execution',
            'type': 'object',
            'additionalProperties': {
                'type': 'array',
                'items': {
                    '$ref': '#/definitions/input_file',
                },
            },
        },
        'tasks': {
            'description': 'The execution configuration for each task',
            'type': 'array',
            'items': {
                '$ref': '#/definitions/task',
            },
        },
    },
    'definitions': {
        'input_file': {
            'type': 'object',
            'required': ['id', 'type', 'workspace_id', 'workspace_path', 'is_deleted'],
            'additionalProperties': False,
            'properties': {
                'id': {
                    'type': 'integer',
                },
                'type': {
                    'type': 'string',
                    'enum': ['SOURCE', 'PRODUCT'],
                },
                'workspace_id': {
                    'type': 'integer',
                },
                'workspace_path': {
                    'type': 'string',
                },
                'local_file_name': {
                    'type': 'string',
                },
                'is_deleted': {
                    'type': 'boolean',
                },
                'data_started': {
                    'type': 'string',
                },
                'data_ended': {
                    'type': 'string',
                },
                'source_started': {
                    'type': 'string',
                },
                'source_ended': {
                    'type': 'string',
                },
            },
        },
        'task': {
            'type': 'object',
            'required': ['type', 'args'],
            'additionalProperties': False,
            'properties': {
                'task_id': {
                    'description': 'The ID of the task',
                    'type': 'string',
                },
                'type': {
                    'description': 'The type of the task',
                    'type': 'string',
                },
                'args': {
                    'description': 'The command argument string for this task',
                    'type': 'string',
                },
                'env_vars': {
                    'description': 'The environment variables for this task',
                    'type': 'object',
                    'additionalProperties': {
                        'type': 'string',
                    },
                },
                'workspaces': {
                    'description': 'The workspaces available to this task',
                    'type': 'object',
                    'additionalProperties': {
                        '$ref': '#/definitions/workspace'
                    },
                },
                'mounts': {
                    'description': 'The mounts for this task',
                    'type': 'object',
                    'additionalProperties': {
                        'anyOf': [
                            {'type': 'string'},
                            {'type': 'null'}
                        ],
                    },
                },
                'settings': {
                    'description': 'The settings for this task',
                    'type': 'object',
                    'additionalProperties': {
                        'anyOf': [
                            {'type': 'string'},
                            {'type': 'null'}
                        ],
                    },
                },
                'volumes': {
                    'description': 'The workspaces available to this task',
                    'type': 'object',
                    'additionalProperties': {
                        '$ref': '#/definitions/volume'
                    },
                },
                'docker_params': {
                    'description': 'The Docker parameters that will be set for this task',
                    'type': 'array',
                    'items': {
                        '$ref': '#/definitions/docker_param',
                    },
                },
            },
        },
        'workspace': {
            'type': 'object',
            'required': ['volume_name', 'mode'],
            'additionalProperties': False,
            'properties': {
                'volume_name': {
                    'type': 'string',
                },
                'mode': {
                    'type': 'string',
                    'enum': [MODE_RO, MODE_RW],
                },
            },
        },
        'volume': {
            'type': 'object',
            'required': ['container_path', 'mode', 'type'],
            'additionalProperties': False,
            'properties': {
                'container_path': {
                    'type': 'string',
                },
                'mode': {
                    'type': 'string',
                    'enum': [MODE_RO, MODE_RW],
                },
                'type': {
                    'type': 'string',
                    'enum': ['host', 'volume'],
                },
                'host_path': {
                    'type': 'string',
                },
                'driver': {
                    'type': 'string',
                },
                'driver_opts': {
                    'type': 'object',
                    'additionalProperties': {
                        'type': 'string',
                    },
                },
            },
        },
        'docker_param': {
            'type': 'object',
            'required': ['flag', 'value'],
            'additionalProperties': False,
            'properties': {
                'flag': {
                    'type': 'string',
                },
                'value': {
                    'type': 'string',
                },
            },
        },
    },
}


class ExecutionConfiguration(object):
    """Represents a job execution configuration
    """

    def __init__(self, configuration=None):
        """Creates an execution configuration from the given JSON dict

        :param configuration: The JSON dictionary
        :type configuration: dict
        :raises :class:`job.configuration.exceptions.InvalidExecutionConfiguration`: If the JSON is invalid
        """

        if not configuration:
            configuration = {}
        self._configuration = configuration

        if 'version' not in self._configuration:
            self._configuration['version'] = SCHEMA_VERSION

        if self._configuration['version'] != SCHEMA_VERSION:
            self._configuration = ExecutionConfiguration._convert_configuration(configuration)

        self._populate_default_values()

        try:
            validate(configuration, EXE_CONFIG_SCHEMA)
        except ValidationError as validation_error:
            raise InvalidExecutionConfiguration(validation_error)

    def configure_for_queued_job(self, job, input_files):
        """Configures this execution for the given queued job. The given job model should have its related job_type and
        job_type_rev models populated.

        :param job: The queued job model
        :type job: :class:`job.models.Job`
        :param input_files: The dict of Scale file models stored by ID
        :type input_files: dict
        """

        data = job.get_job_data()
        self._add_input_files(data, input_files)

        # Set up env vars for job's input data
        env_vars = {}
        # TODO: refactor this to use JobData method after Seed upgrade
        for data_input in data.get_dict()['input_data']:
            input_name = data_input['name']
            env_var = input_name.upper()  # Environment variable names are all upper case
            if 'value' in data_input:
                env_vars[env_var] = data_input['value']
            if 'file_id' in data_input:
                file_dict = self._configuration['input_files'][input_name][0]
                file_name = os.path.basename(file_dict['workspace_path'])
                if 'local_file_name' in file_dict:
                    file_name = file_dict['local_file_name']
                env_vars[env_var] = os.path.join(SCALE_JOB_EXE_INPUT_PATH, input_name, file_name)
            elif 'file_ids' in data_input:
                env_vars[env_var] = os.path.join(SCALE_JOB_EXE_INPUT_PATH, input_name)

        # Add env var for output directory
        # TODO: original output dir can be removed when Scale only supports Seed-based job types
        env_vars['job_output_dir'] = SCALE_JOB_EXE_OUTPUT_PATH  # Original output directory
        env_vars['OUTPUT_DIR'] = SCALE_JOB_EXE_OUTPUT_PATH  # Seed output directory

        main_task_dict = {'type': 'main', 'args': job.get_job_interface().get_command_args(), 'env_vars': env_vars}
        self._configuration['tasks'] = [main_task_dict]

    def get_dict(self):
        """Returns the internal dictionary that represents this execution configuration

        :returns: The internal dictionary
        :rtype: dict
        """

        return self._configuration

    def _add_input_files(self, job_data, input_files):
        """Adds the given input files to the configuration

        :param job_data: The job data
        :type job_data: :class:`job.configuration.data.job_data.JobData`
        :param input_files: The dict of Scale file models stored by ID
        :type input_files: dict
        """

        files_dict = {}

        for input_name, file_ids in job_data.get_input_file_ids_by_input().items():
            file_list = []
            file_names = set()
            for file_id in file_ids:
                scale_file = input_files[file_id]
                file_dict = {'id': scale_file.id, 'type': scale_file.file_type, 'workspace_id': scale_file.workspace_id,
                             'workspace_path': scale_file.file_path, 'is_deleted': scale_file.is_deleted}
                # Check for file name collision and use Scale file ID to ensure names are unique
                file_name = scale_file.file_name
                if file_name in file_names:
                    file_name = '%d.%s' % (scale_file.id, file_name)
                    file_dict['local_file_name'] = file_name
                file_names.add(file_name)
                file_list.append(file_dict)
            files_dict[input_name] = file_list

        self._configuration['input_files'] = files_dict

    @staticmethod
    def _convert_configuration(configuration):
        """Converts the given execution configuration to the 2.0 schema

        :param configuration: The previous configuration
        :type configuration: dict
        :return: The converted configuration
        :rtype: dict
        """

        previous = previous_version.ExecutionConfiguration(configuration)

        converted = previous.get_dict()

        converted['version'] = SCHEMA_VERSION

        ExecutionConfiguration._convert_configuration_task(converted, 'pre', 'pre_task')
        ExecutionConfiguration._convert_configuration_task(converted, 'main', 'job_task')
        ExecutionConfiguration._convert_configuration_task(converted, 'post', 'post_task')

        return converted

    @staticmethod
    def _convert_configuration_task(configuration, task_type, old_task_name):
        """Converts the given task in the configuration

        :param configuration: The configuration to convert
        :type configuration: dict
        :param task_type: The type of the task
        :type task_type: string
        :param old_task_name: The old task name
        :type old_task_name: string
        """

        if old_task_name not in configuration:
            return

        old_task_dict = configuration[old_task_name]
        new_task_dict = {"task_id": old_task_name, "type": task_type, "args": ""}

        if 'workspaces' in old_task_dict:
            new_workspace_dict = {}
            new_task_dict['workspaces'] = new_workspace_dict
            for old_workspace in old_task_dict['workspaces']:
                name = old_workspace['name']
                mode = old_workspace['mode']
                new_workspace_dict[name] = {'mode': mode, 'volume_name': 'wksp_%s' % name}

        if 'settings' in old_task_dict:
            new_settings_dict = {}
            new_task_dict['settings'] = new_settings_dict
            for old_setting in old_task_dict['settings']:
                name = old_setting['name']
                value = old_setting['value']
                new_settings_dict[name] = value

        if 'docker_params' in old_task_dict:
            new_params_list = []
            new_task_dict['docker_params'] = new_params_list
            for old_param in old_task_dict['docker_params']:
                new_params_list.append(old_param)

        if 'tasks' not in configuration:
            configuration['tasks'] = []
        configuration['tasks'].append(new_task_dict)
        del configuration[old_task_name]

    def _populate_default_values(self):
        """Populates any missing JSON fields that have default values
        """

        if 'input_files' not in self._configuration:
            self._configuration['input_files'] = {}
        if 'tasks' not in self._configuration:
            self._configuration['tasks'] = []

    # TODO: phase all of this out and replace it

    def add_job_task_setting(self, name, value):
        """Adds a setting name/value to this job's job task

        :param name: The setting name to add
        :type name: string
        :param value: The setting value to add
        :type value: string
        """

        pass

    def add_post_task_setting(self, name, value):
        """Adds a setting name/value to this job's post task

        :param name: The setting name to add
        :type name: string
        :param value: The setting value to add
        :type value: string
        """

        pass

    def add_pre_task_setting(self, name, value):
        """Adds a setting name/value to this job's pre task

        :param name: The setting name to add
        :type name: string
        :param value: The setting value to add
        :type value: string
        """

        pass

    def add_job_task_docker_params(self, params):
        """Adds the given Docker parameters to this job's job task

        :param params: The Docker parameters to add
        :type params: [:class:`job.configuration.job_parameter.DockerParam`]
        """

        pass

    def add_post_task_docker_params(self, params):
        """Adds the given Docker parameters to this job's post task

        :param params: The Docker parameters to add
        :type params: [:class:`job.configuration.job_parameter.DockerParam`]
        """

        pass

    def add_pre_task_docker_params(self, params):
        """Adds the given Docker parameters to this job's pre task

        :param params: The Docker parameters to add
        :type params: [:class:`job.configuration.job_parameter.DockerParam`]
        """

        pass

    def add_job_task_workspace(self, name, mode):
        """Adds a needed workspace to this job's job task

        :param name: The name of the workspace
        :type name: string
        :param mode: The mode of the workspace, either MODE_RO or MODE_RW
        :type mode: string
        """

        pass

    def add_post_task_workspace(self, name, mode):
        """Adds a needed workspace to this job's post task

        :param name: The name of the workspace
        :type name: string
        :param mode: The mode of the workspace, either MODE_RO or MODE_RW
        :type mode: string
        """

        pass

    def add_pre_task_workspace(self, name, mode):
        """Adds a needed workspace to this job's pre task

        :param name: The name of the workspace
        :type name: string
        :param mode: The mode of the workspace, either MODE_RO or MODE_RW
        :type mode: string
        """

        pass

    def get_job_task_settings(self):
        """Returns the settings name/values needed for the job task

        :returns: The job task settings name/values
        :rtype: [:class:`job.configuration.job_parameter.TaskSetting`]
        """

        return []

    def get_post_task_settings(self):
        """Returns the settings name/values needed for the post task

        :returns: The post task settings name/values
        :rtype: [:class:`job.configuration.job_parameter.TaskSetting`]
        """

        return []

    def get_pre_task_setting(self):
        """Returns the settings name/values needed for the pre task

        :returns: The pre task settings name/values
        :rtype: [:class:`job.configuration.job_parameter.TaskSetting`]
        """

        return []

    def get_job_task_docker_params(self):
        """Returns the Docker parameters needed for the job task

        :returns: The job task Docker parameters
        :rtype: [:class:`job.configuration.job_parameter.DockerParam`]
        """

        return []

    def get_post_task_docker_params(self):
        """Returns the Docker parameters needed for the post task

        :returns: The post task Docker parameters
        :rtype: [:class:`job.configuration.job_parameter.DockerParam`]
        """

        return []

    def get_pre_task_docker_params(self):
        """Returns the Docker parameters needed for the pre task

        :returns: The pre task Docker parameters
        :rtype: [:class:`job.configuration.job_parameter.DockerParam`]
        """

        return []

    def get_job_task_workspaces(self):
        """Returns the workspaces needed for the job task

        :returns: The job task workspaces
        :rtype: [:class:`job.configuration.job_parameter.TaskWorkspace`]
        """

        return []

    def get_post_task_workspaces(self):
        """Returns the workspaces needed for the post task

        :returns: The post task workspaces
        :rtype: [:class:`job.configuration.job_parameter.TaskWorkspace`]
        """

        return []

    def get_pre_task_workspaces(self):
        """Returns the workspaces needed for the pre task

        :returns: The pre task workspaces
        :rtype: [:class:`job.configuration.job_parameter.TaskWorkspace`]
        """

        return []

    def configure_workspace_docker_params(self, job_exe, workspaces, docker_volumes):
        """Configures the Docker parameters needed for each workspace in the job execution tasks. The given job
        execution must have been set to RUNNING status.

        :param job_exe: The job execution model (must not be queued) with related job and job_type fields
        :type job_exe: :class:`job.models.JobExecution`
        :param workspaces: A dict of all workspaces stored by name
        :type workspaces: {string: :class:`storage.models.Workspace`}
        :param docker_volumes: A list to add Docker volume names to
        :type docker_volumes: [string]

        :raises Exception: If the job execution is still queued
        """

        pass

    def configure_logging_docker_params(self, job_exe):
        """Configures the Docker parameters needed for job execution logging

        :param job_exe: The job execution model (must not be queued) with related job and job_type fields
        :type job_exe: :class:`job.models.JobExecution`

        :raises Exception: If the job execution is still queued
        """

        pass

    def populate_default_job_settings(self, job_exe):
        """Gathers the job settings defined in the job_type and populates the execution configuration with them

        :param job_exe: The job execution model with related job and job_type fields
        :type job_exe: :class:`job.models.JobExecution`
        """

        interface = job_exe.get_job_interface()
        job_config = job_exe.get_job_configuration()
        for setting in interface.get_dict()['settings']:
            if not setting['secret']:
                setting_name = setting['name']
                setting_value = job_config.get_setting_value(setting_name)
                if setting_value:
                    self.add_job_task_setting(setting_name, setting_value)

    def populate_mounts(self, job_exe):
        """Adds the mounts defined in the job type's interface and configuration to the execution configuration

        :param job_exe: The job execution model with related job and job_type fields
        :type job_exe: :class:`job.models.JobExecution`
        """

        pass
        # interface = job_exe.get_job_interface()
        # job_config = job_exe.get_job_configuration()
        # for mount in interface.get_dict()['mounts']:
        #     name = mount['name']
        #     mode = mount['mode']
        #     path = mount['path']
        #     volume_name = get_mount_volume_name(job_exe, name)
        #     volume = job_config.get_mount_volume(name, volume_name, path, mode)
        #     if volume:
        #         self.add_job_task_docker_params([volume.to_docker_param()])