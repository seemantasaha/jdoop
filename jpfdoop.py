#!/usr/bin/env python

# The main JPF-Doop program file. It is used to run JPF-Doop to
# generate unit tests.

import os, sys, shutil
import argparse
import ConfigParser

from symbolize_tests import *
from generate_jpf_files import *
from command import *
from report import *

class ClassList:
    def __init__(self, filename):
        self.filename = filename
        self.list_of_classes = None

    def get_all_java_source_files(self, base, rootdir):
        """Finds all java files in a given directory tree and returns a list of such files"""

        if not self.list_of_classes == None:
            return self.list_of_classes

        ret = []
        
        for dirpath, dirnames, filenames in os.walk(os.path.join(base, rootdir)):
            for name in filenames:
                if name.endswith('.java'):
                    # No need to worry about abstract classes nor
                    # interfaces because Randoop will take care of
                    # that
                    ret.append(dirpath[len(os.path.normpath(base)) + 1:].replace("/", ".") + "." + name[:-len(".java")])

        self.list_of_classes = ret

        return ret

    def write_list_of_classes(self, root, rel_path):
        """Writes to a file a list of classes to be tested by JPFDoop"""

        with open(self.filename, 'w') as f:
            f.write("\n".join(self.get_all_java_source_files(root, rel_path)) + "\n")
        

class UnitTests:
    def __init__(self, name = "Randoop1Test", directory = "tests-1st-round"):
        self.directory = directory
        self.name = name
        self.randooped_package_name = "randooped"

class Paths:
    def __init__(self):
        pass

class RandoopRun:
    def __init__(self, unit_tests_name, unit_tests_directory, classlist_filename, timelimit, unit_tests_number_upper_limit, paths, use_concrete_values = False):
        self.unit_tests_name = unit_tests_name
        self.unit_tests_directory = unit_tests_directory
        self.classlist_filename = classlist_filename
        self.unit_tests_timelimit = timelimit
        self.unit_tests_number_upper_limit = unit_tests_number_upper_limit
        self.paths = paths
        self.use_concrete_values = use_concrete_values

    def run(self):

        # Remove previous unit tests
        
        shutil.rmtree(self.unit_tests_directory, ignore_errors = True)
        try:
            os.makedirs(self.unit_tests_directory)
        except:
            pass

        # Invoke Randoop. Check if it should use concrete values

        if not self.use_concrete_values:
            concrete_values_str = ""
        else:
            concrete_values_str = " --literals-file=concrete-values.txt --literals-level=ALL"

        command = Command(args = "java -ea -cp " + ":".join([self.paths.lib_randoop, self.paths.lib_junit, self.paths.sut_compilation_dir]) + " randoop.main.Main gentests --classlist=" + self.classlist_filename + " --junit-output-dir=" + self.unit_tests_directory + " --junit-classname=" + self.unit_tests_name + " --timelimit=%s" % self.unit_tests_timelimit + " --outputlimitrandom=%s" % self.unit_tests_number_upper_limit + " --forbid-null=false --small-tests=true" + concrete_values_str)

        command.run()

class JPFDoop:
    def __init__(self):
        pass
        self.paths = Paths()

    def read_config_file(self, config_file_name):
        config = ConfigParser.RawConfigParser()
        config.read(config_file_name)

        sections = ['jpfdoop', 'sut', 'tests', 'lib']
        for section in sections:
            if not config.has_section(section):
                sys.exit("The configuration file does not have the [" + section + "] section!")

        try:
            self.jpf_core_path = str(config.get('jpfdoop', 'jpf-core'))
            self.jpf_jdart_path = str(config.get('jpfdoop', 'jpf-jdart'))
            self.paths.sut_compilation_dir = str(config.get('sut', 'compilation-directory'))
            self.paths.tests_compilation_dir = str(config.get('tests', 'compilation-directory'))
            self.paths.lib_junit = str(config.get('lib', 'junit'))
            self.paths.lib_randoop = str(config.get('lib', 'randoop'))
            self.paths.lib_jacoco = str(config.get('lib', 'jacoco'))
        except Exception, err:
            print str(err) + " in " + config_file_name
            sys.exit(1)

    def run_randoop(self, unit_tests, classlist, params, runittests = 100000000, use_concrete_values = False):
        """Invokes Randoop"""

        randoop_run = RandoopRun(unit_tests.name, unit_tests.directory, classlist.filename, str(params.rtimelimit), str(runittests), self.paths, use_concrete_values)
        randoop_run.run()

    def compile_tests(self, unit_tests):
        """Compiles unit tests generated by Randoop"""

        try:
            os.makedirs(self.paths.tests_compilation_dir)
        except:
            pass

        compile_tests_command = Command(args = "javac -g -d " + self.paths.tests_compilation_dir + " -cp " + ":".join([self.paths.sut_compilation_dir, self.paths.lib_junit]) + " " + unit_tests.directory + "/*java")
        compile_tests_command.run()

    def compile_symbolic_tests(self, root_dir, unit_tests):
        """Compiles JDart-modified symbolic unit tests"""

        try:
            os.makedirs(self.paths.tests_compilation_dir)
        except:
            pass

        compile_tests_command = Command(args = "javac -g -d " + self.paths.tests_compilation_dir + " -cp " + ":".join([os.path.join(self.jpf_jdart_path, "build"), os.path.join(self.jpf_jdart_path, "build/annotations/"), self.paths.sut_compilation_dir, self.paths.tests_compilation_dir, self.paths.lib_junit]) + " " + os.path.join(root_dir, unit_tests.randooped_package_name +  "/*java"))
        compile_tests_command.run()

    def symbolize_unit_tests(self, unit_tests, root_dir):
        """Replaces concrete method input values with symbolic variables in unit tests"""

        symbolic_unit_tests = SymbolicUnitTests(unit_tests.randooped_package_name, root_dir, "classes-to-analyze", os.path.join(unit_tests.directory, unit_tests.name + '0.java'))
        symbolic_unit_tests.generate_symbolized_unit_tests()

    def generate_jpf_conf(self, unit_tests, root_dir):
        """Generates JPF configuration files (.jpf) for JDart"""
        
        jpf_configuration_files = CoordinateConfFileGeneration(unit_tests.randooped_package_name, root_dir, 'classes-to-analyze', ",".join([self.paths.tests_compilation_dir, self.paths.lib_junit]))
        jpf_configuration_files.run()

    def run_jdart(self, unit_tests, root_dir):
        """Calls JDart on the symbolized unit tests"""

        with open(os.path.join(root_dir, unit_tests.randooped_package_name, "classes-to-analyze")) as f:
            for line_nl in f:
                class_name = line_nl[:-1]

                whole_path = os.path.join(root_dir, unit_tests.randooped_package_name, class_name + ".jpf")

                jdart = CommandWithTimeout(cmd=os.path.join(self.jpf_core_path, "bin/jpf"), args=os.path.join(self.jpf_core_path, "bin/jpf") + " " + whole_path)
                jdart.run(timeout=20)

    def put_class_name(self, classlist, root_dir, path):
        """Replaces a placeholder with a valid class name in the file with concrete values"""

        put_class_name_command = Command(args = "python put-class-name.py --classname %s" % classlist.get_all_java_source_files(root_dir, path)[0])
        put_class_name_command.run()

    def run_code_coverage(self, unit_tests_list, package_path):
        """Runs JaCoCo on all unit tests from the list and generates a code coverage report"""

        # Run tests for all unit test sets but the last one
        for uts in unit_tests_list[:-1]:
            code_coverage_command = Command(args = "ant -f jacoco.xml -Darg0=%s -Darg1=%s test" % (uts.name, package_path))
            code_coverage_command.run()

        # Run tests for the last unit test set and generate a report
        report_command = Command(args = "ant -f jacoco.xml -Darg0=%s -Darg1=%s report" % (unit_tests_list[-1].name, package_path))
        report_command.run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generates unit tests with Randoop only or with JPF-Doop.')
    parser.add_argument('--packagename', required=True, help='A Java package with classes to analyze.')
    parser.add_argument('--path', required=True, help='path within the root directory to the source files')
    parser.add_argument('--root', default='src/examples/', help='source files root directory')
    parser.add_argument('--classlist', default='classlist.txt', help='Name of a file to write a file list to')
    parser.add_argument('--rtimelimit', default=30, help='Timelimit for a single run of Randoop')
    parser.add_argument('--runittests', default=20, help='Upper limit of number of unit tests Randoop will generate in a single run')
    parser.add_argument('--conffile', default='jpfdoop.ini', help="A configuration file with settings for JPF-Doop")
    params = parser.parse_args()

    # Create a list of classes to be tested
    classlist = ClassList(params.classlist)
    classlist.write_list_of_classes(params.root, params.path)

    jpfdoop = JPFDoop()
    jpfdoop.read_config_file(params.conffile)

    unit_tests = UnitTests(name = "Randoop1Test", directory = "tests-1st-round")

    # Invoke Randoop to generate unit tests
    jpfdoop.run_randoop(unit_tests, classlist, params, params.runittests)

    # Symbolize unit tests
    jpfdoop.symbolize_unit_tests(unit_tests, params.root)

    # Generate JPF configuration files
    jpfdoop.generate_jpf_conf(unit_tests, params.root)

    # Compile symbolized unit tests
    jpfdoop.compile_symbolic_tests(params.root, unit_tests)

    # Run JDart on symbolized unit tests
    jpfdoop.run_jdart(unit_tests, params.root)

    # Replace a placeholder with a valid class name in the file with
    # concrete values
    jpfdoop.put_class_name(classlist, params.root, params.path)

    unit_tests2 = UnitTests(name = "Randoop2Test", directory = "tests-2nd-round")

    # Run Randoop for the second time
    jpfdoop.run_randoop(unit_tests2, classlist, params, use_concrete_values = True)
    
    # Compile tests generated by Randoop
    jpfdoop.compile_tests(unit_tests)
    jpfdoop.compile_tests(unit_tests2)
    
    # Generate a code coverage report
    unit_tests_list = [unit_tests.name, unit_tests2.name]
    classpath = ":".join([jpfdoop.paths.lib_junit, jpfdoop.paths.sut_compilation_dir, jpfdoop.paths.tests_compilation_dir])
    report = Report(jpfdoop.paths.lib_jacoco, unit_tests_list, os.path.normpath(params.path), classpath, params.root, jpfdoop.paths.sut_compilation_dir)
    report.run_code_coverage()
