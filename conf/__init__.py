import importlib
import os
import time
from skuld.conf import global_settings
from skuld.core.exceptions import ImproperlyConfigured
from skuld.utils.functional import LazyObject, empty


ENVIRONMENT_VARIABLE = 'SKULD_SETTINGS_MODULE'


class Settings:
    def __init__(self, settings_module):
        for setting in dir(global_settings):
            if setting.isupper():
                setattr(self, setting, getattr(global_settings, setting))

        self.SETTINGS_MODULE = settings_module

        mod = importlib.import_module(self.SETTINGS_MODULE)

        tuple_settings = ('INSTALLED_APPS')

        self._explicit_settings = set()
        for setting in dir(mod):
            if setting.isupper():
                setting_value = getattr(mod, setting)

                if (setting in tuple_settings and
                        not isinstance(setting_value, (list, tuple))):
                    raise ImproperlyConfigured(f'The {setting} setting must be a list or a tuple.')
                setattr(self, setting, setting_value)
                self._explicit_settings.add(setting)

        if not self.SECRET_KEY:
            raise ImproperlyConfigured('The SECRET_KEY setting must not be empty.')

        if hasattr(time, 'tzset') and self.TIME_ZONE:
            os.environ['TZ'] = self.TIME_ZONE
            time.tzset()

    def is_overridden(self, setting):
        return setting in self._explicit_settings

    def __repr__(self):
        return '<{self.__class__.__name__} "{self.SETTINGS_MODULE}">'


class SettingsHolder:
    SETTINGS_MODULE = None

    def __init__(self, default_settings):
        self.__dict__['_deleted'] = set()
        self.default_settings = default_settings

    def __getattr__(self, name):
        if name in self._deleted:
            raise AttributeError
        return getattr(self.default_settings, name)

    def __setattr__(self, name, value):
        self._deleted.discard(name)
        super().__setattr__(name, value)

    def __delattr__(self, name):
        self._deleted.add(name)
        if hasattr(self, name):
            super().__delattr__(name)

    def __dir__(self):
        return sorted(
            s for s in [*self.__dict__, *dir(self.default_settings)]
            if s not in self._deleted
        )

    def is_overridden(self, setting):
        deleted = (setting in self._deleted)
        set_locally = (setting in self.__dict__)
        set_on_default = getattr(self.default_settings, 'is_overridden', lambda s: False)(setting)
        return deleted or set_locally or set_on_default

    def __repr__(self):
        return f'<{self.__class__.__name__}>'


class LazySettings(LazyObject):

    def _setup(self, name=None):
        settings_module = os.environ.get(ENVIRONMENT_VARIABLE)
        if not settings_module:
            desc = (f'setting {name}') if name else 'settings'
            raise ImproperlyConfigured(
                f'Requested {desc}, but settings are not configured. '
                f'You must either define the environment variable {ENVIRONMENT_VARIABLE} '
                'or call settings.configure() before accessing settings.')

        self._wrapped = Settings(settings_module)

    def __repr__(self):
        if self._wrapped is empty:
            return '<LazySettings [Unevaluated]>'
        return f'<LazySettings "{self._wrapped.SETTINGS_MODULE}">'

    def __getattr__(self, name):
        if self._wrapped is empty:
            self._setup(name)
        val = getattr(self._wrapped, name)
        self.__dict__[name] = val
        return val

    def __setattr__(self, name, value):
        if name == '_wrapped':
            self.__dict__.clear()
        else:
            self.__dict__.pop(name, None)
        super().__setattr__(name, value)

    def __delattr__(self, name):
        super().__delattr__(name)
        self.__dict__.pop(name, None)

    def configure(self, default_settings=global_settings, **options):
        if self._wrapped is not empty:
            raise RuntimeError('Settings already configured.')
        holder = SettingsHolder(default_settings)
        for name, value in options.items():
            setattr(holder, name, value)
        self._wrapped = holder

    @property
    def configured(self):
        return self._wrapped is not empty

settings = LazySettings()
