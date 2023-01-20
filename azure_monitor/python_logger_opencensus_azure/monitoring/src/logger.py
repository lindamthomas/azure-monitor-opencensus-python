"""This module is used to log traces into Azure Application Insights."""
import functools
import logging
import uuid
from os import getenv

from opencensus.ext.azure.common import utils
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace import config_integration
from opencensus.trace.samplers import AlwaysOffSampler, AlwaysOnSampler
from opencensus.trace.tracer import Tracer
from opencensus.ext.flask.flask_middleware import FlaskMiddleware
from opencensus.trace.samplers import ProbabilitySampler


class SingletonLoggerFactory(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonLoggerFactory, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
    
class CustomDimensionsFilter(logging.Filter):
    """Add custom-dimensions in each log by using filters."""

    def __init__(self, custom_dimensions=None):
        """Initialize CustomDimensionsFilter."""
        self.custom_dimensions = custom_dimensions or {}

    def filter(self, record):
        """Add the default custom_dimensions into the current log record."""
        dim = {**self.custom_dimensions, **getattr(record, "custom_dimensions", {})}
        record.custom_dimensions = dim
        return True


class AppLogger(object, metaclass=SingletonLoggerFactory):
    """Logger wrapper that attach the handler to Application Insights."""

    HANDLER_NAME = "Azure Application Insights Handler"

    def __init__(self, config=None):
        """Create an instance of the Logger class.

        Args:
            config:([dict], optional):
                Contains the setting for logger {"log_level": "DEBUG","logging_enabled":"true"",
                                    "app_insights_key":"<app insights key>"}
        """
        config_integration.trace_integrations(["logging"])
        config_integration.trace_integrations(['requests'])
        self.config = {"log_level": logging.INFO, "logging_enabled": "true"}
        self.APPINSIGHTS_INSTRUMENTATION_KEY = "APPINSIGHTS_INSTRUMENTATION_KEY"
        self.update_config(config)
        self.handler = self._initialize_azure_log_handler()


    def _initialize_azure_log_handler(self):
        """Initialize azure log handler."""
        # Adding logging to trace_integrations
        # This will help in adding trace and span ids to logs
        # https://github.com/census-instrumentation/opencensus-python/tree/master/contrib/opencensus-ext-logging

        logging.basicConfig(
            format="%(asctime)s name=%(name)s level=%(levelname)s "
            "traceId=%(traceId)s spanId=%(spanId)s %(message)s"
        )
        app_insights_cs = "InstrumentationKey=" + self._get_app_insights_key()
        log_handler = AzureLogHandler(
            connection_string=app_insights_cs, export_interval=5.0
        )
        log_handler.name = self.HANDLER_NAME
        
        return log_handler

    def _get_trace_exporter(self, component_name="AppLogger"):
        """[Get log exporter]

        Returns:
            [AzureExporter]: [Azure Trace Exporter]
        """
        app_insights_cs = "InstrumentationKey=" + self._get_app_insights_key()
        log_exporter = AzureExporter(
                        connection_string=app_insights_cs, sampler=ProbabilitySampler(1.0)
                    )
        log_exporter.add_telemetry_processor(self._get_callback(component_name))
        return log_exporter

    def _initialize_logger(self, component_name, custom_dimensions):
        """Initialize Logger."""
        logger = logging.getLogger(component_name)
        logger.setLevel(self.log_level)
        if self.config.get("logging_enabled") == "true":
            if not any(x for x in logger.handlers if x.name == self.HANDLER_NAME):
                logger.addHandler(self.handler)
        self.handler.addFilter(CustomDimensionsFilter(custom_dimensions))
        self.handler.add_telemetry_processor(self._get_callback(component_name))
        return logger


    def get_logger(self, component_name="AppLogger", custom_dimensions={}):
        """Get Logger Object.

        Args:
            component_name (str, optional): Name of logger. Defaults to "AppLogger".
            custom_dimensions (dict, optional): {"key":"value"} to capture with every log.
                Defaults to {}.

        Returns:
            Logger: A logger.
        """
        self.update_config(self.config)
        return self._initialize_logger(component_name, custom_dimensions)

    def get_tracer(self, component_name="AppLogger", parent_tracer=None):
        """Get Tracer Object.

        Args:
            component_name (str, optional): Name of logger. Defaults to "AppLogger".
            parent_tracer([opencensus.trace.tracer], optional):
                Contains parent tracer required for setting coorelation.

        Returns:
            opencensus.trace.tracer: A Tracer.
        """
        self.update_config(self.config)
        sampler = AlwaysOnSampler()
        exporter = self._get_trace_exporter(component_name)
        if self.config.get("logging_enabled") != "true":
            sampler = AlwaysOffSampler()
        if parent_tracer is None:
            tracer = Tracer(exporter=exporter, sampler=sampler)
        else:
            tracer = Tracer(
                span_context=parent_tracer.span_context,
                exporter=exporter,
                sampler=sampler,
            )
        return tracer

    def enable_flask(self,flask_app,component_name="AppLogger"):
        """Enable flask for tracing
        For more info : https://github.com/census-instrumentation/opencensus-python/blob/master/contrib/opencensus-ext-flask/opencensus/ext/flask/flask_middleware.py

        Args:
            flask_app ([type]): [description]
            component_name (str, optional): [description]. Defaults to "AppLogger".
        """
        FlaskMiddleware(
            flask_app, exporter=self._get_trace_exporter(component_name=component_name)
            )

    def _get_app_insights_key(self):
        """Get Application Insights Key."""
        try:
            if self.app_insights_key is None:
                self.app_insights_key = getenv(
                    self.APPINSIGHTS_INSTRUMENTATION_KEY, None
                )
            if self.app_insights_key is not None:
                utils.validate_instrumentation_key(self.app_insights_key)
                return self.app_insights_key
            else:
                raise Exception("ApplicationInsights Key is not set")
        except Exception as exp:
            raise Exception(f"Exception is getting app insights key-> {exp}")

    def _get_callback(self, component_name):
        """Adding cloud role name. This is required to give the name of component in application map.
        https://docs.microsoft.com/azure/azure-monitor/app/app-map?tabs=net#understanding-cloud-role-name-within-the-context-of-the-application-map

        Args:
            component_name ([str]): [The name of the component or applicaiton]
        """
        def _callback_add_role_name(envelope):
            """Add role name for logger."""
            envelope.tags["ai.cloud.role"] = component_name
            envelope.tags["ai.cloud.roleInstance"] = component_name

        return _callback_add_role_name

    def update_config(self, config=None):
        """Update logger configuration."""
        if config is not None:
            self.config.update(config)
        self.app_insights_key = self.config.get("app_insights_key")
        self.log_level = self.config.get("log_level")


