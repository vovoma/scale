"""Defines the JSON schema for describing the job configuration"""
from __future__ import unicode_literals

import logging

from jsonschema import validate
from jsonschema.exceptions import ValidationError

from job.configuration.exceptions import InvalidExecutionConfiguration
from job.configuration.job_parameter import TaskSetting
from job.configuration.json.execution import exe_config_1_0 as previous_version
from job.configuration.volume import MODE_RO, MODE_RW
from job.execution.container import get_mount_volume_name

logger = logging.getLogger(__name__)


SCHEMA_VERSION = '1.1'


EXE_CONFIG_SCHEMA = {
    'type': 'object',
    'required': ['job_task'],
    'additionalProperties': False,
    'properties': {
        'version': {
            'description': 'Version of the execution configuration schema',
            'type': 'string',
            'pattern': '^.{0,50}$',
        },
        'pre_task': {'$ref': '#/definitions/task'},
        'job_task': {'$ref': '#/definitions/task'},
        'post_task': {'$ref': '#/definitions/task'},
    },
    'definitions': {
        'task': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'docker_params': {
                    'type': 'array',
                    'items': {
                        '$ref': '#/definitions/docker_param',
                    },
                },
                'settings': {
                    'type': 'array',
                    'items': {
                        '$ref': '#/definitions/setting',
                    },
                },
                'workspaces': {
                    'type': 'array',
                    'items': {
                        '$ref': '#/definitions/workspace',
                    },
                },
            },
        },
        'workspace': {
            'type': 'object',
            'required': ['name', 'mode'],
            'additionalProperties': False,
            'properties': {
                'name': {
                    'type': 'string',
                },
                'mode': {
                    'type': 'string',
                    'enum': [MODE_RO, MODE_RW],
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
        'setting': {
            'type': 'object',
            'required': ['name', 'value'],
            'additionalProperties': False,
            'properties': {
                'name': {
                    'type': 'string',
                },
                'value': {
                    'type': 'string',
                },
            },
        },
    },
}


class ExecutionConfiguration(previous_version.ExecutionConfiguration):
    """Represents a job configuration
    """

    def __init__(self, configuration=None):
        """Creates an execution configuration from the given JSON dict

        :param configuration: The JSON dictionary
        :type configuration: dict
        :raises :class:`job.configuration.exceptions.InvalidExecutionConfiguration`: If the JSON is invalid
        """

        if not configuration:
            configuration = {'job_task': {'docker_params': []}}
        self._configuration = configuration
        self._pre_task_workspace_names = set()
        self._job_task_workspace_names = set()
        self._post_task_workspace_names = set()

        self._pre_task_setting_names = set()
        self._job_task_setting_names = set()
        self._post_task_setting_names = set()

        if 'version' not in self._configuration:
            self._configuration['version'] = SCHEMA_VERSION

        if self._configuration['version'] != SCHEMA_VERSION:
            self.convert_configuration(configuration)

        try:
            validate(configuration, EXE_CONFIG_SCHEMA)
        except ValidationError as validation_error:
            raise InvalidExecutionConfiguration(validation_error)

        self._populate_default_values()
        self._populate_default_settings()
        self._validate_workspace_names()
        self._validate_setting_names()

    @staticmethod
    def convert_configuration(configuration):
        """Convert the previous Job configuration schema to the 1.1 schema

        :param configuration: The previous configuration
        :type configuration: dict
        :return: converted configuration
        :rtype: dict
        """
        previous = previous_version.ExecutionConfiguration(configuration)

        converted = previous.get_dict()

        converted['version'] = SCHEMA_VERSION

        if 'settings' not in converted['pre_task']:
            converted['pre_task']['settings'] = []

        if 'settings' not in converted['job_task']:
            converted['job_task']['settings'] = []

        if 'settings' not in converted['post_task']:
            converted['post_task']['settings'] = []

        return converted

    def add_job_task_setting(self, name, value):
        """Adds a setting name/value to this job's job task

        :param name: The setting name to add
        :type name: string
        :param value: The setting value to add
        :type value: string
        """

        self._configuration['job_task']['settings'].append({'name': name, 'value': str(value)})

    def add_post_task_setting(self, name, value):
        """Adds a setting name/value to this job's post task

        :param name: The setting name to add
        :type name: string
        :param value: The setting value to add
        :type value: string
        """

        self._configuration['post_task']['settings'].append({'name': name, 'value': str(value)})

    def add_pre_task_setting(self, name, value):
        """Adds a setting name/value to this job's pre task

        :param name: The setting name to add
        :type name: string
        :param value: The setting value to add
        :type value: string
        """

        self._configuration['pre_task']['settings'].append({'name': name, 'value': str(value)})

    def get_job_task_settings(self):
        """Returns the settings name/values needed for the job task

        :returns: The job task settings name/values
        :rtype: [:class:`job.configuration.job_parameter.TaskSetting`]
        """

        params = self._configuration['job_task']['settings']
        return [TaskSetting(param_dict['name'], param_dict['value']) for param_dict in params]

    def get_post_task_settings(self):
        """Returns the settings name/values needed for the post task

        :returns: The post task settings name/values
        :rtype: [:class:`job.configuration.job_parameter.TaskSetting`]
        """

        params = self._configuration['post_task']['settings']
        return [TaskSetting(param_dict['name'], param_dict['value']) for param_dict in params]

    def get_pre_task_setting(self):
        """Returns the settings name/values needed for the pre task

        :returns: The pre task settings name/values
        :rtype: [:class:`job.configuration.job_parameter.TaskSetting`]
        """

        params = self._configuration['pre_task']['settings']
        return [TaskSetting(param_dict['name'], param_dict['value']) for param_dict in params]

    def _populate_default_settings(self):
        """Populates any missing JSON fields for settings
        """

        if 'settings' not in self._configuration['pre_task']:
            self._configuration['pre_task']['settings'] = []

        if 'settings' not in self._configuration['job_task']:
            self._configuration['job_task']['settings'] = []

        if 'settings' not in self._configuration['post_task']:
            self._configuration['post_task']['settings'] = []

    def _validate_setting_names(self):
        """Ensures that no tasks have duplicate setting names

        :raises :class:`job.configuration.exceptions.InvalidExecutionConfiguration`: If there is a duplicate setting
            name
        """

        for setting_dict in self._configuration['pre_task']['settings']:
            name = setting_dict['name']
            if name in self._pre_task_setting_names:
                raise InvalidExecutionConfiguration('Duplicate setting %s in pre task' % name)
            self._pre_task_setting_names.add(name)
        for setting_dict in self._configuration['job_task']['settings']:
            name = setting_dict['name']
            if name in self._job_task_setting_names:
                raise InvalidExecutionConfiguration('Duplicate setting %s in job task' % name)
            self._job_task_setting_names.add(name)
        for setting_dict in self._configuration['post_task']['settings']:
            name = setting_dict['name']
            if name in self._post_task_setting_names:
                raise InvalidExecutionConfiguration('Duplicate setting %s in post task' % name)
            self._post_task_setting_names.add(name)

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

        interface = job_exe.get_job_interface()
        job_config = job_exe.get_job_configuration()
        for mount in interface.get_dict()['mounts']:
            name = mount['name']
            mode = mount['mode']
            path = mount['path']
            volume_name = get_mount_volume_name(job_exe, name)
            volume = job_config.get_mount_volume(name, volume_name, path, mode)
            if volume:
                self.add_job_task_docker_params([volume.to_docker_param()])
