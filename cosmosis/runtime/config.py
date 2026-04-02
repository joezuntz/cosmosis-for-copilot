#coding: utf-8


u"""Definition of the :class:`Config` and :class:`Inifile` classes."""


import os
import sys
import collections
import configparser
import io


class CosmosisConfigurationError(configparser.Error):
    u"""Something to throw when there is an error in a .ini file particular to Cosmosis.

    The (underlying) object simply carries a string providing information
    to the user.

    """
    pass


class Config:
    u"""A dictionary of `(section, name) -> value` pairs holding configuration information.

    This class stores configuration data in a section/key structure and provides
    typed accessors to retrieve values as strings, integers, floats, booleans, or
    arrays.  It can be constructed directly from a dictionary or from another
    :class:`Config` instance.

    The values are all stored as strings internally, with methods provided to
    locate and interpret them as integers, floating-point numbers, booleans, or
    arrays of integers or floating-point numbers.

    """

    def __init__(self, data=None, defaults=None, override=None):
        u"""Create a Config from in-memory data.

        Args:
            data: optional initial configuration data.  May be:

                * ``None`` – create an empty configuration,
                * a :class:`dict` mapping ``section -> {key: value}`` pairs, or
                * another :class:`Config` instance to copy.

            defaults: default values applied when a parameter is absent
                (populates the DEFAULT section).
            override: a mapping of ``(section, name) -> value`` pairs that are
                set unconditionally, overriding any value already present.

        """
        # _sections stores per-section key→value dicts (section-specific only,
        # not including DEFAULT values).
        self._sections = collections.OrderedDict()
        # _defaults stores values from the [DEFAULT] section.
        self._defaults = collections.OrderedDict()

        if isinstance(defaults, dict):
            for k, v in defaults.items():
                self._defaults[k.lower()] = str(v)

        if isinstance(data, dict):
            for section, values in data.items():
                self.add_section(section)
                for key, value in values.items():
                    self.set(section, key, str(value))
        elif isinstance(data, Config):
            self._defaults.update(data._defaults)
            for section in data.sections():
                self.add_section(section)
                for name, value in data.items(section, defaults=False):
                    self._sections[section][name] = value
        elif data is not None:
            raise TypeError(f"Config data must be a dict or Config instance, not {type(data)}")

        if override:
            for section, name in override:
                if section == "DEFAULT":
                    self._defaults[name.lower()] = str(override[(section, name)])
                else:
                    if not self.has_section(section):
                        self.add_section(section)
                    self.set(section, name, override[(section, name)])

    # ------------------------------------------------------------------
    # Section management
    # ------------------------------------------------------------------

    def sections(self):
        u"""Return a list of section names (excluding DEFAULT)."""
        return list(self._sections.keys())

    def has_section(self, section):
        u"""Return True if the named section exists."""
        return section in self._sections

    def add_section(self, section):
        u"""Create a new empty section.  Raise DuplicateSectionError if it already exists."""
        if section in self._sections:
            raise configparser.DuplicateSectionError(section)
        self._sections[section] = collections.OrderedDict()

    def set(self, section, option, value):
        u"""Set an option value in the given section."""
        option = option.lower()
        value = str(value)
        if section == "DEFAULT":
            self._defaults[option] = value
        elif section not in self._sections:
            raise configparser.NoSectionError(section)
        else:
            self._sections[section][option] = value

    def has_option(self, section, option):
        u"""Return True if `option` exists in `section` or in the DEFAULT section."""
        option = option.lower()
        return (
            (section in self._sections and option in self._sections[section])
            or option in self._defaults
        )

    def options(self, section):
        u"""Return a list of all option names for `section`, including DEFAULT values."""
        if not self.has_section(section):
            raise configparser.NoSectionError(section)
        d = collections.OrderedDict(self._defaults)
        d.update(self._sections[section])
        return list(d.keys())

    def remove_option(self, section, option):
        u"""Remove `option` from `section`.  Return True if it was present."""
        option = option.lower()
        if section == "DEFAULT":
            if option in self._defaults:
                del self._defaults[option]
                return True
            return False
        if not self.has_section(section):
            raise configparser.NoSectionError(section)
        if option in self._sections[section]:
            del self._sections[section][option]
            return True
        return False

    def remove_section(self, section):
        u"""Remove `section` and all its options.  Return True if the section existed."""
        if section in self._sections:
            del self._sections[section]
            return True
        return False

    # ------------------------------------------------------------------
    # Iteration and item access
    # ------------------------------------------------------------------

    def __iter__(self):
        u"""Iterate over all the parameters.

        The value of the iterator is `((section, name), value)`.

        """
        return (((section, name), value) for section in self.sections()
                for name, value in self.items(section))

    def __getitem__(self, key: tuple):
        section, option = key
        return self.get(section, option)

    def __setitem__(self, key: tuple, value: str):
        section, option = key
        self.set(section, option, str(value))

    def items(self, section, raw=False, vars=None, defaults=True):
        u"""Return a list of pairs (key, value) from all the options in a given `section`.

        If `section` is ``"DEFAULT"``, returns items from the DEFAULT section.

        If defaults is True (the default), parameters in the [DEFAULT] section are
        included in all other sections.

        If vars is set to a dictionary, use it as an additional source of options
        (takes highest precedence).

        The `raw` parameter is accepted for API compatibility but has no effect
        (values are always returned as stored strings).

        """
        if section == "DEFAULT":
            d = collections.OrderedDict(self._defaults)
            if vars:
                for key, value in vars.items():
                    d[key.lower()] = str(value)
            return list(d.items())
        if not self.has_section(section):
            raise configparser.NoSectionError(section)
        d = collections.OrderedDict()
        if defaults:
            d.update(self._defaults)
        d.update(self._sections[section])
        if vars:
            for key, value in vars.items():
                d[key.lower()] = str(value)
        return list(d.items())

    # ------------------------------------------------------------------
    # Typed getters
    # ------------------------------------------------------------------

    def get(self, section, option, raw=False, vars=None, fallback=configparser._UNSET):
        u"""Get a value as a string, or `fallback` if the value is not in the dictionary.

        If `fallback` is not set and is needed, a :class:`CosmosisConfigurationError`
        will be raised. (`None` is *not* acceptable as a fallback).

        The `raw` parameter is accepted for API compatibility but has no effect.

        """
        option = option.lower()
        # vars take highest precedence
        if vars and option in {k.lower() for k in vars}:
            for k, v in vars.items():
                if k.lower() == option:
                    return str(v)
        # Check section-specific value
        if section in self._sections and option in self._sections[section]:
            return self._sections[section][option]
        # Check defaults
        if option in self._defaults:
            return self._defaults[option]
        # Not found
        if fallback is not configparser._UNSET:
            return fallback
        raise CosmosisConfigurationError(
            "CosmoSIS looked for an option called '%s' in the '[%s]' section, "
            "but it was not in the ini file" % (option, section))

    def getint(self, section, option, raw=False, vars=None, fallback=configparser._UNSET):
        u"""Get a value as an integer, or return `fallback` if the value is not found.

        If `fallback` is not set and is needed, a :class:`CosmosisConfigurationError`
        will be raised.

        """
        try:
            value = self.get(section, option, raw=raw, vars=vars)
            return int(value)
        except CosmosisConfigurationError:
            if fallback is configparser._UNSET:
                raise CosmosisConfigurationError(
                    "CosmoSIS looked for an integer option called '%s' in the '[%s]' section, "
                    "but it was not in the ini file" % (option, section))
            elif not isinstance(fallback, int):
                raise TypeError("Default not integer")
            else:
                return fallback

    def getfloat(self, section, option, raw=False, vars=None, fallback=configparser._UNSET):
        u"""Get a floating-point value from the dictionary, with `fallback`.

        If the value is not found in the dictionary and `fallback` is specified,
        then `fallback` will be returned.  Otherwise a :class:`CosmosisConfigurationError`
        will be thrown with a useful message for the user.

        """
        try:
            value = self.get(section, option, raw=raw, vars=vars)
            return float(value)
        except CosmosisConfigurationError:
            if fallback is configparser._UNSET:
                raise CosmosisConfigurationError(
                    "CosmoSIS looked for a float option called '%s' in the '[%s]' section, "
                    "but it was not in the ini file" % (option, section))
            elif not isinstance(fallback, float):
                raise TypeError("Default not float")
            else:
                return fallback

    def getboolean(self, section, option, raw=False, vars=None, fallback=configparser._UNSET):
        u"""Interpret a parameter as a boolean, including symbolic values.

        This essentially allows a configuration file to represent boolean
        values in the most convenient manner ('true', 'n', etc) as well as
        with zero/non-zero numerical values.

        If the parameter is not found in the dictionary, then `fallback`
        will be returned, which will itself default to `False` if not
        specified.

        """
        _true_values = {'1', 'yes', 'true', 'on', 'y', 't'}
        _false_values = {'0', 'no', 'false', 'off', 'n', 'f'}
        try:
            value = self.get(section, option, raw=raw, vars=vars)
            lower = value.lower()
            if lower in _true_values:
                return True
            elif lower in _false_values:
                return False
            else:
                raise ValueError("Unable to parse parameter "
                                  "%s--%s = %s into boolean form"
                                  % (section, option, value))
        except CosmosisConfigurationError:
            if fallback is configparser._UNSET:
                raise CosmosisConfigurationError(
                    "CosmoSIS looked for a boolean (T/F) option called '%s' in the '[%s]' section, "
                    "but it was not in the ini file" % (option, section))
            elif not isinstance(fallback, bool):
                raise TypeError("Default not boolean")
            else:
                return fallback

    def gettyped(self, section, name):
        u"""Best-guess the type of a parameter and return it as that type.

        The method will try parsing the value as, in this order:
            an integer or list of integers,
            a float or list of floats,
            a complex number or list of complex numbers,
            a boolean,
            a string.

        The string value is the fallback if all else fails.
        """

        import re

        value = self.get(section, name)
        value = value.strip()
        # There isn't really a sensible thing to return for this,
        # so we just need to set it to None.
        if not value:
            return None
        # try quoted string
        m = re.match(r"^(['\"])(.*?)\1$", value)
        if m is not None:
            return m.group(2)

        value_list = value.split()

        # Try to match integer array.  This will fail whenever a decimal
        # point occurs anywhere in the list of values.
        try:
            parsed = [int(s) for s in value_list]
            if len(parsed) == 1:
                return parsed[0]
            else:
                return parsed
        except ValueError:
            pass

        # try to match float array
        try:
            parsed = [float(s) for s in value_list]
            if len(parsed) == 1:
                return parsed[0]
            else:
                return parsed
        except ValueError:
            pass

        # try to match complex array
        try:
            parsed = [complex(s) for s in value_list]
            if len(parsed) == 1:
                return parsed[0]
            else:
                return parsed
        except ValueError:
            pass

        # try to match boolean (no array support)
        try:
            return self.getboolean(section, name)
        except ValueError:
            pass

        # default to string
        return value

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def write(self, fp):
        u"""Write the configuration in .ini format to `fp`."""
        if self._defaults:
            fp.write("[DEFAULT]\n")
            for key, value in self._defaults.items():
                fp.write("{} = {}\n".format(key, str(value).replace('\n', '\n\t')))
            fp.write("\n")
        for section, options in self._sections.items():
            fp.write("[{}]\n".format(section))
            for key, value in options.items():
                fp.write("{} = {}\n".format(key, str(value).replace('\n', '\n\t')))
            fp.write("\n")


class IncludingConfigParser(configparser.ConfigParser):
    u"""Extension of built-in python :class:`ConfigParser` to %include other files.

    Use the line: %include filename.ini This is assumed to end a section,
    and the last section in the included file is assumed to end as well

    Note that the caller of the `read()` method may set a
    `no_expand_includes` attribute on this object, to cause any %include
    lines to *not* actually be actioned (they will be regarded as
    comments, but still delineate sections).
    """

    def __init__(self, defaults=None, print_include_messages=True, no_expand_vars=False):
        self.no_expand_vars = no_expand_vars
        configparser.ConfigParser.__init__(self,
                                           defaults=defaults,
                                           dict_type=collections.OrderedDict,
                                           strict=False,
                                           inline_comment_prefixes=(';', '#'),
                                           )
        self.print_include_messages = print_include_messages

    def _read(self, fp, fpname):
        """
        This overrides the parent method to allow %include directives
        to import additional files.

        To do so we first read the file into a StringIO object, dealing
        with the %include directives as we go, then pass that to the
        parent method.
        """
        s = io.StringIO()
        for line in fp:
            # check for include directives
            if not self.no_expand_vars:
                line = os.path.expandvars(line)

            if line.lower().startswith('%include'):
                _, filename = line.split()
                filename = filename.strip('"').strip("'")

                if self.print_include_messages:
                    print(f"Reading included ini file: {filename}")
                if not os.path.exists(filename):
                    raise ValueError(f"Tried to include non-existent file {filename}")

                # read the contents of the ini file into a new Inifile instance,
                # then we will write it out
                sub_ini = Inifile(filename)

                # write the whole other file content to our StringIO
                sub_ini.write(s)
            else:
                s.write(line)

        # rewind the stuff we have read
        s.seek(0)
        return super()._read(s, fpname)



class Inifile(Config):

    u"""Reads a .ini file and makes its contents available as a :class:`Config`.

    The class is designed to hide the details of parsing .ini files, and
    then for creating :class:`DataBlock` objects (which wrap C objects
    and can be passed down a processing pipeline which may include modules
    written in C) via the :class:`Pipeline` and then :class:`Module`
    constructors (see `Pipeline.__init__()`).

    Configuration data is accessed through the methods inherited from
    :class:`Config`.

    """

    def __init__(self, filename, defaults=None, override=None, print_include_messages=True, no_expand_vars=False):
        u"""Read in a configuration from `filename`.

        The `defaults` will be applied if a parameter is not specified in
        the file (or %included descendants), and the `override`s will be
        imposed on the regardless of whether those parameters have
        assigned values or not.

        Where supplied, `defaults` and `override` should be dictionary
        mappings of `(section, name) -> value`.

        `filename` may be:

        * a path to an .ini file (string),
        * a :class:`Config` instance to copy,
        * a :class:`dict` mapping ``section -> {key: value}``,
        * a file-like object with a ``read()`` method, or
        * ``None`` for an empty configuration.

        """
        super().__init__(defaults=defaults)
        self._print_include_messages = print_include_messages
        self._no_expand_vars = no_expand_vars

        # if we are passed a dict, populate section by section
        if isinstance(filename, dict):
            for section, values in filename.items():
                self.add_section(section)
                for key, value in values.items():
                    self.set(section, key, str(value))
        elif isinstance(filename, Config):
            self._defaults.update(filename._defaults)
            for section in filename.sections():
                self.add_section(section)
                for name, value in filename.items(section, defaults=False):
                    self._sections[section][name] = value
        elif hasattr(filename, "read"):
            parser = self._make_parser()
            parser.read_file(filename)
            self._load_from_parser(parser)
        # default read behaviour is to ignore unreadable files which
        # is probably not what we want here
        elif filename is not None:
            if isinstance(filename, str) and not os.path.exists(filename):
                raise IOError("Unable to open configuration file `" + filename + "'")
            parser = self._make_parser()
            parser.read(filename)
            self._load_from_parser(parser)

        # override parameters
        if override:
            for section, name in override:
                if section == "DEFAULT":
                    self._defaults[name.lower()] = str(override[(section, name)])
                else:
                    if not self.has_section(section):
                        self.add_section(section)
                    self.set(section, name, override[(section, name)])

    def _make_parser(self):
        u"""Create an :class:`IncludingConfigParser` with this instance's settings."""
        return IncludingConfigParser(
            print_include_messages=self._print_include_messages,
            no_expand_vars=self._no_expand_vars,
        )

    def _load_from_parser(self, parser):
        u"""Transfer parsed data from an :class:`IncludingConfigParser` into this Config."""
        # Copy DEFAULT values
        for key, value in parser.defaults().items():
            self._defaults[key] = str(value)
        # Copy section-specific values.
        # parser._sections[section] holds only the values defined directly in
        # that section (not including inherited DEFAULT values), which is
        # exactly what we want to store separately in Config._sections.
        for section in parser.sections():
            if not self.has_section(section):
                self.add_section(section)
            for key, value in parser._sections[section].items():
                self._sections[section][key] = str(value)

    def read_string(self, string):
        u"""Parse ini-format text and merge the result into this Config."""
        parser = self._make_parser()
        parser.read_string(string)
        self._load_from_parser(parser)

    def read_file(self, fp):
        u"""Parse ini-format text from a file-like object and merge into this Config."""
        parser = self._make_parser()
        parser.read_file(fp)
        self._load_from_parser(parser)

    @classmethod
    def from_lines(cls, lines, *args, **kwargs):
        u"""Create an Inifile from a list of lines."""
        s = io.StringIO("\n".join(lines))
        return cls(s, *args, **kwargs)
