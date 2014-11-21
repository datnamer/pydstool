# -*- coding: utf-8 -*-
"""
Various useful mixins for Generators
"""

from __future__ import print_function, absolute_import

from abc import abstractproperty, ABCMeta
import os
import shutil
import sys

from numpy import get_include
from numpy.distutils.core import setup, Extension

from PyDSTool import utils
import PyDSTool.Redirector as redirc

# path to the installation
import PyDSTool
_pydstool_path = PyDSTool.__path__[0]
_sourcedir = os.path.join(_pydstool_path, "integrator")


_all__ = ['CompiledMixin']


class CompiledMixin:
    """Abstract mixin for compilable generators

    Subclasses *must* implement :py:attr:`integrator` property, which defines
    necessary data for used integrator.

    Also adds following property and methods related to building extension
    module for vector-field integration:
        - :py:attr:`modname`: name of extension module.

        - :py:meth:`makeLibSource`: generates source file for VF spec.

        - :py:meth:`compileLib`: generates Python extension with integrator and
            VF compiled and linked.

        - :py:meth:`forceLibRefresh`: deletes extension module from current
            session.

            .. warning::
                Currently this function does NOT work!

        - :py:meth:`makeLib`: convenient wrapper, which consequently calls
            :py:meth:`forceLibRefresh` (if necessary), :py:meth:`makeLibSource`
            and :py:meth:`compileLib`.
    """

    __metaclass__ = ABCMeta

    @abstractproperty
    def integrator(self):
        return {}

    @property
    def modname(self):
        return self._builder.modname

    def makeLibSource(self, include=[], fname=None):
        """makeLibSource generates the C source for the vector field specification.
        It should be called only once per vector field."""

        code = self.funcspec.generate_user_module(
            self.eventstruct,
            name=self._builder.integrator_name,
            include=include)
        self._builder.save_vfield(code, fname)

    def compileLib(self, libsources=None, libdirs=None):
        """compileLib generates a python extension DLL with integrator and vector
        field compiled and linked.

        libsources list allows additional library sources to be linked.
        libdirs list allows additional directories to be searched for
          precompiled libraries."""

        self._builder.build(libsources, libdirs, self._compiler)

    def forceLibRefresh(self):
        """forceLibRefresh should be called after event contents are changed,
        or alterations are made to the right-hand side of the ODEs.

        Currently this function does NOT work!"""

        print("Cannot rebuild library without restarting session. Sorry.")
        print("Try asking the Python developers to make a working module")
        print("unimport function!")

    def makeLib(self, libsources=[], libdirs=[], include=[]):
        """makeLib calls makeLibSource and then the compileLib method.
        To postpone compilation of the source to a DLL, call makeLibSource()
        separately."""

        if self._solver is not None:
            self.forceLibRefresh()
        self.makeLibSource(include)
        self.compileLib(libsources, libdirs)

    @property
    def _builder(self):
        if not hasattr(self, '_builder_ref'):
            self._builder_ref = _Builder(self.name, self.integrator)
        return self._builder_ref


class _Builder(object):
    """Helper object which performs extension module building"""

    def __init__(self, vfname, integrator):
        self.integrator = integrator
        self.libname = integrator['name'][0]
        self.integrator_name = integrator['name'][1]
        self.description = integrator['description']
        self.sources = full_path(self.integrator['src'])
        self.cflags = integrator.get('cflags', [])
        self.libs = integrator.get('libs', [])

        self.vfname = vfname + "_vf"
        self.modname = "{0}_{1}_vf".format(self.libname, vfname)
        self.tempdir = os.path.join(os.getcwd(), self.libname + "_temp")

        if not os.path.isdir(self.tempdir):
            _prepare_tempdir(self.tempdir)

    @property
    def pyfile(self):
        return self.modname + ".py"

    @property
    def extfile(self):
        return "_" + self.modname + utils.get_lib_extension()

    def build(self, libsources=None, libdirs=None, compiler=None):
        if _exists(self.extfile):
            # DLL file already exists and we can't overwrite it at this time
            self._fail()
            return

        common = ["integration.c", "interface.c", "eventFinding.c", "memory.c"]
        sources = [os.path.join(self.tempdir, self.vfname + ".c")]
        sources.extend(self.sources)
        sources.extend(full_path(common))
        sources.extend(libsources or [])

        # The following if statement attempts to avoid recompiling the SWIG
        # wrapper if the files mentioned already exist, because in principle
        # the SWIG interface only needs compiling once. But this step doesn't
        # seem to work yet.  Instead, it seems that SWIG always gets recompiled
        # with everything else (at least on Win32). Maybe the list of files is
        # incorrect...
        swigfile = self._prepare_swig_file()
        files = [t.format(self.modname)
                 for t in ['{0}_wrap.o', 'lib_{0}.a', '{0}.py', '_{0}.def']]
        if not all(_exists(f, self.tempdir) for f in files):
            sources.append(swigfile)

        script_args = [
            "build_ext",
            "--inplace",
            "-q",
            "--build-temp={0}".format(self.tempdir),
        ]
        if compiler:
            script_args.append("-c" + str(compiler))

        # include directories for libraries
        incdirs = [get_include()]
        incdirs.extend([os.getcwd(), _sourcedir])
        incdirs.extend(libdirs or [])
        # Use distutils to perform the compilation of the selected files
        rout = redirc.Redirector(redirc.STDOUT)
        rout.start()    # redirect stdout
        try:
            extmod = Extension(
                "_" + self.modname,
                sources=sources,
                include_dirs=incdirs,
                extra_compile_args=utils.extra_arch_arg(
                    ["-w", "-Wno-return-type"]) + self.cflags,
                extra_link_args=utils.extra_arch_arg(["-w"]),
                libraries=self.libs
            )

            setup(name=self.description,
                  author="PyDSTool (automatically generated)",
                  script_args=script_args,
                  ext_modules=[extmod],
                  py_modules=[self.modname])

            # move library files into the user's CWD
            if swigfile in sources or not _exists(self.pyfile, self.tempdir):
                # temporary hack to fix numpy_distutils bug
                shutil.move(
                    os.path.join(os.getcwd(), self.tempdir, self.pyfile),
                    os.path.join(os.getcwd(), self.pyfile))
        except IOError:
            print("\nError occurred in generating '%s' system" % self.vfname)
            print("(while moving library extension modules to CWD)")
            print("%s %s" % (sys.exc_info()[0], sys.exc_info()[1]))
            raise RuntimeError
        except Exception:
            print("\n")
            print("Error occurred in generating '%s' system..." % self.vfname)
            print("%s %s" % (sys.exc_info()[0], sys.exc_info()[1]))
            raise RuntimeError
        finally:
            rout.stop()    # restore stdout

    def done(self):
        """Check if all files generated"""
        return all(_exists(f) for f in [self.pyfile, self.extfile])

    def save_vfield(self, code, fname=None):
        """Save code for vector-field to file"""

        vf = fname or os.path.join(self.tempdir, self.vfname + ".c")
        try:
            with open(vf, "w") as f:
                f.write(code)
        except IOError as e:
            print("Error opening file %s for writing" % vf)
            raise IOError(e)

    def _prepare_swig_file(self):
        """Copy SWIG interface from PyDSTool to building directory"""

        src_path = os.path.join(_sourcedir, "%s.i" % self.libname)
        dest_path = os.path.join(self.tempdir, self.modname + ".i")

        try:
            with open(dest_path, "w") as dest:
                dest.write("%module " + self.modname + "\n")
                with open(src_path, "r") as src:
                    dest.write(src.read())
        except IOError as e:
            print("{name}.i copying error in {name} compilation directory:"
                  " {msg}".format(name=self.libname, msg=e))
            raise
        return dest_path

    def _fail(self):
        print("\n")
        print("-----------------------------------------------------------")
        print("Present limitation of Python: Cannot rebuild library")
        print("without exiting Python and deleting the shared library")
        print("   %s" % str(os.path.join(os.getcwd(), self.extfile)))
        print("by hand! If you made any changes to the system you should")
        print("not proceed with running the integrator until you quit")
        print("and rebuild.")
        print("-----------------------------------------------------------")
        print("\n")
        print("Did not compile shared library.")


def full_path(fs):
    return [os.path.join(_sourcedir, f) for f in fs]


def _exists(f, d=None):
    d = d or os.getcwd()
    return os.path.isfile(os.path.join(d, f))


def _prepare_tempdir(tempdir):
    try:
        if os.path.isfile(tempdir):
            raise NameError("A file already exists with the same name")
        os.mkdir(tempdir)
    except IOError:
        print("Could not create compilation temp directory %s" % tempdir)
        raise
