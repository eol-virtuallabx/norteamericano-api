from django.apps import AppConfig
from openedx.core.djangoapps.plugins.constants import (
    PluginSettings,
    PluginURLs,
    ProjectType,
    SettingsType,
)


class NorteamericanoAPIConfig(AppConfig):
    name = 'norteamericanoapi'
    plugin_app = {
        PluginURLs.CONFIG: {
            ProjectType.CMS: {
                PluginURLs.NAMESPACE: "norteamericanoapi",
                PluginURLs.REGEX: r"^norteamericano_api/",
                PluginURLs.RELATIVE_PATH: "urls",
            },
            ProjectType.LMS: {
                PluginURLs.NAMESPACE: "norteamericanoapi",
                PluginURLs.REGEX: r"^norteamericano_api/",
                PluginURLs.RELATIVE_PATH: "urls_lms",
            },
        },
        PluginSettings.CONFIG: {
            ProjectType.CMS: {
                SettingsType.COMMON: {
                    PluginSettings.RELATIVE_PATH: "settings.common"}},
            ProjectType.LMS: {
                SettingsType.COMMON: {
                    PluginSettings.RELATIVE_PATH: "settings.common"}},
        },
    }
