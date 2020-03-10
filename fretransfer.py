#!/usr/bin/env python3

import configparser
import subprocess
import argparse
import datetime
import logging
import fnmatch
import shutil
import glob
import stat
import sys
import re
import os

base_repo_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
template_dir = os.path.join(base_repo_dir, "templates")
template_names = ["historyArgfileTemplate.txt", "restartArgfileTemplate.txt", 
                  "asciiArgfileTemplate.txt"]
argFile_types = ["history", "restart", "ascii"]
templates = {k:template_dir + v for (k,v) in zip(argFile_types, template_names)}

freRunArgCfg = os.path.join(base_repo_dir, "freRunArgs.cfg")
freDefArgCfg = os.path.join(base_repo_dir, "freDefArgs.cfg")

config_userDefs = configparser.ConfigParser()
config_frerun = configparser.ConfigParser()

logging_format = '%(levelname)s: %(message)s'


class ExtendAction(argparse.Action):
    """
    A class introduced to register a new function into the argparse module

    Inheritance: argparse.Action

    """
    def __call__(self, parser, namespace, values, option_string=None):
        """
        Allows argparse to extend the end of a list, rather than its default
        of merely appending a new list

        Parameters (5):
        - self: the ExtendAction object
        - parser: the argparse parser object
        - namespace: the argparse namespace
        - values: items in the argparse list
        - option_string: an optional string for argparse

        Returns (0):
        - None

        """
        items = getattr(namespace, self.dest) or []
        items.extend(values)
        setattr(namespace, self.dest, items)


class ArgumentError(Exception):
    """
    Creates an exception specifically for fretransfer argument usage

    Inheritance: Exception class

    """ 
    pass


# Class for argFile to create with a template   
class argFile:
    """ 
    Builds a container around the attributes of an .args file, which references
    essential states of a FRE program, in this case, output.stager

    Inheritance: None

    """  
    def __init__(self, fileType, newFilePath, *args):
        """
        Initialize an object that creates attributes to the .args file using a
        template, which is checked for its existence.

        Parameters (3):
        - fileType (str): The type of .args file being created (i.e. history, 
                         restart, ascii)
        - newFilePath (str): Path of newly written .args file
        - *args: Additional arguments needed

        Returns:
        None

        """
    
        self.fileType = fileType

        if os.path.isfile(templates[fileType]):
            self.templateLocation = templates[fileType]
        else:
            raise FileNotFoundError("The %s template file %s does not exist." % (fileType, templates[fileType]))

        filePatterns = []
        # get the full path of new argFile 
        self.newFileLocation = argFile.new_file(self, newFilePath)

        # get list of files to process
        argFile.get_file_list(self, self.fileType, filePatterns)
 
    
    # each new file has a rootFilePath set to None by default    
    # the new file is placed in {newFilePath}/{fileType}
    @staticmethod
    def new_file(self, rootFilePath):
        """
        Retrieve the file path of a newly created .args file

        Parameters(1):
        - rootFilePath(str): The base directory for the final location

        Returns (1):
        - Final path for the new .args file

        """

        fileName = argFile.get_new_file_name(self)
        return os.path.join(rootFilePath, fileName)

    
    @staticmethod
    def get_new_file_name(self):
        """
        Builds a string containing a date and time for the newly created
        .args file

        Parameters (0):
        - None

        Returns (1):
        - newFileName (str): String with a filename containing a time stamp
                             for history, restart, and ascii .args files

        """

        fileNameRoot = 'output.stager.'

        if self.fileType == 'ascii':
           beginDate = get_time_stamp('-b')
           fileNameAppendix = beginDate + '.A.args'

        elif self.fileType == 'restart':
           endDate = get_time_stamp('-e')
           fileNameAppendix = endDate + '.R.args'

        elif self.fileType == 'history':
            beginDate = get_time_stamp('-b')
            fileNameAppendix = beginDate + '.H.args'

        newFileName = fileNameRoot + fileNameAppendix
        return newFileName


    @staticmethod
    def get_file_list(self, fileType, filePatterns):
        """
        Gather and store a list of all the files needed for staging
        via output.stager based upon the file type desired, i.e.
        history, restart, and ascii

        Parameters (2):
        - fileType (str): 'ascii', 'history', or 'restart'
        - filePatterns (str): General list of file patterns to investigate from

        Returns (0):
        - None

        """

        if any(filePatterns):
           patternMatch = filePatterns
        elif fileType == 'ascii': 
           patternMatch = ['*out','*results*','*log*','*timestats*','*stats*','*velocity_truncations*']
        elif fileType == 'restart':
            patternMatch = ['*res*','*nc*','*.input.*tgz','*.ww3']
        elif fileType == 'history':
            patternMatch = ['*nc*','*.ww3']
        
        names = os.listdir('.')
        self.fileList = multi_filter(names, patternMatch)


def write_file(filePath, fileStatus="", **kwargs):
    """
    Write out the values of all the arguments listed in the temporary file
    to the new .args file

    Parameters (2)
    - fileStatus (str): In 'write' or 'append' mode. Must be either/or.
    - **kwargs: Unpacking of a dictionary with the key/value pairs of arguments

    Returns (0):
    - None

    """
    
    if fileStatus != "w":
        if fileStatus != "a":
            raise ValueError("fileStatus must be 'w' or 'a'")
           
    shutil.copy(filePath, filePath + "~" )

    # read in lines from the temporary sourceFile
    with open(filePath + "~", "r") as h:
        lines = h.readlines()

    # replace lines with values if they exist
    for key, value in kwargs.items():
        logging.info("%s %s" % (key, str(value)))
        for index, line in enumerate(lines):
            if key in line:
                if 'setenv'in line:
                    lines[index] = 'setenv ' + key + '' + str(value)
                else:
                    lines[index] = 'set ' + key + ' = ' + str(value)

                break
              
    # write values to argFile
    with open(filePath, fileStatus) as j:
        for line in lines:
            if len(line.strip()) > 0:
                j.write(line + "\n")

    # remove the temporary file
    filePathParts = os.path.split(filePath)
    clean_dir(filePathParts[0], [filePathParts[1] + '~'])


#Generator function which yields a list of names that match one or more of the patterns."""       
def multi_filter(names, patterns):
    """
    Generator function which yields a list of names that match one or more of the
    file patterns.

    Parameters (2)
    - names (str): A list of file strings all within the current working directory
    - patterns (str): A list of strings that describe a search filter for certain files

    Returns (1)
    - A list of all of the matched files based off the patterns given

    """

    fileList = []
    for name in names:
        for pattern in patterns:
            if fnmatch.fnmatch(name, pattern) and name not in fileList:
                fileList.append(name)
    return fileList

                
def clean_dir(pathName, removeFilePatterns):
    """
    Function to help clear a directory of unnecessary files based upon a search
    patterns

    Parameters (2):
    - pathName (str): The base directory for the deletion searching
    - removeFilePatterns (str): The patterns to identify files for removal

    Returns (0):
    - None

    """

    os.chdir(pathName)
    for pattern in removeFilePatterns:
        fileList = glob.glob(pattern)
        for file in fileList:
            os.remove(file)
    
               
def copy_file(srcPath, destPath):
    """
    Copies a new .args file to the appropriate path and creates directories
    if necessary.

    Paramters (2):
    - srcPath (str): Original path of .args file
    - destPath (str): New path of .args file copied from srcPath

    Returns (0):
    None

    """

    pathParts = os.path.split(destPath)
    if not os.path.isdir(pathParts[0]):
        os.makedirs(pathParts[0])
        
    shutil.copyfile(srcPath, destPath)
    if not os.path.isfile(destPath):
        raise FileNotFoundError("File %s was not created" % destPath)
   
 
def pexec(arg, *args):
    """
    Executes a command based upon the given subparser arguments

    Paramters (2):
    - arg (str): Initial argument
    - *args (list): List of arguments from subparser

    Returns (1)
    - A Python subprocess object

    """

    argList = []
    argList.append(arg)
 
    for a in args:
        argList.append(''.join(a)) 

    return subprocess.Popen(argList, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def get_host_name():
    """
    Retrieves the machine HOST name. Raises an error if the hostname is not
    GFDL, Gaea, or Theia.

    Parameters (0):
    - None

    Returns (1)
    - The machine HOST name

    """

    hostName = os.environ['HOST']
    if any([re.search(r, hostName) for r in ['gfdl.noaa.gov', 'gaea', 'theia']]):
        return hostName
    else:
        raise OSError('Error: $HOST is not gfdl, gaea, or theia. Exiting.')


def get_fre_dir():
    """
    Retrieve the directory containing the repository for the FRE source code and
    .args template files (their eventual final destination).

    Parameters (0):
    - None

    Returns (1):
    - The base FRE directory

    """

    hostName = get_host_name()
    freVersion = get_fre_version()
    if 'gfdl.noaa.gov' in hostName:
        freDir = '/home/fms/local/opt/fre-commands/' + freVersion + '/site/gfdl-ws'
    elif 'gaea' in hostName:
        freDir = '/ncrc/home2/fms/local/opt/fre-commands/'  + freVersion + '/site/ncrc_common'
    elif 'theia' in hostName:
        freDir = '/home/fms/local/opt/fre-commands/' + freVersion +  '/site/theia' 
        
    return freDir


# return the fre module file version currently loaded in the environment
def get_fre_version():
    """
    Retrieve the current FRE module version loaded in the environment.

    Parameters (0)
    - None

    Returns (1)
    - The FRE version loaded

    """

    moduleVersion = os.environ['MODULE_VERSION']

    moduleCmd = '/opt/cray/pe/modules/' + moduleVersion + '/bin/modulecmd' #gaea modules
    p = pexec(moduleCmd, "tcsh", "list")

    # Read stdout and print each new line
    sys.stdout.flush()
    for line in iter(p.stdout.readline, b''):
        sys.stdout.flush()
        lineStr = line.decode()

        # search for the fre version
        if 'bronx-' in lineStr:
           useline = lineStr.strip()
           searchResult = re.search(r'(?<=fre/)\S*', lineStr)
           freVersion = searchResult.group(0)

           break
    
    return freVersion


def get_time_stamp(*args):
    """
    Function that creates a time stamp to append to the temporary argFiles and
    directory.

    Parameters (1):
    - *args: Argument string for the date

    Returns (1):
    - A datetime string to attach to the temp files

    """

    baseDir = get_fre_dir()
    
    cmd = os.path.join(baseDir.split("/site")[0], 'sbin', 'time_stamp.csh')
    if not os.path.isfile(cmd):
        raise FileNotFoundError("time_stamp.csh not found in the fre root directory")

    p = pexec(cmd, args)
    
    # Read stdout and print each new line
    sys.stdout.flush()
    for line in iter(p.stdout.readline, b''):
        sys.stdout.flush()
        lineStr = line.decode()

        # return a string appendix `tmp(DOY)(HHMMSS)`
        if 'no_time_stamp' in lineStr:
           wereAtNowNow = datetime.datetime.now()
           dateStr = wereAtNowNow.strftime("%Y.%m.%d")
           dt = datetime.datetime.strptime(dateStr, "%Y.%m.%d")
           tt = dt.timetuple()
          
           dateStr = "tmp" + str(tt.tm_yday) + wereAtNowNow.strftime("%H%M%S")
           break
        else:
           dateStr = lineStr.strip()
           break
       
    return dateStr


def add_argparse_arguments(configparser_obj, argparse_obj):
    """
    Helper function that inserts individual "sections" of a config file
    into an argparse object via its method "add_argument". It places
    the key, value pairings of a section into a dictionary and unpacks
    that dictionary into ArgumentParser.add_argument(). Special key, value
    relationships containing Python reserved words must be maintained and
    are demarcated by a preceding underscore (_) in the config file. These
    are parsed via Python's 'eval' method after the underscore is removed.

    Parameters (2):
    - configparser_obj: An object from the configparser.ConfigParser() class
    - argparse_obj: An object from the argparse.ArgumentParser() class

    Returns (0):
    - None

    """

    for section in configparser_obj.sections():
        arg_dict = dict(configparser_obj[section])
        for key, value in arg_dict.items():
            if key != "help" and '!' in value:
                arg_dict[key] = eval(value.replace('!', ''))

        argparse_obj.add_argument(section, **arg_dict)

    argparse_obj.add_argument('-v', '--verbose', action='store_true', 
                              help="Optional. Display extra info regarding creation of argFiles")


def get_sourcepath(args, ftype):
    """
    Helper function for main() which retrieves the source path of the
    working directory housing the 'ascii', 'history', and 'restart' files

    Parameters (2):
    - args: ArgParse object
    - ftype: The type of files fretransfer is dealing with

    Returns (1):
    - The path to the source directory.

    """

    if not (ftype == 'ascii' or ftype == 'restart' or ftype == 'history'):
        raise ValueError("Invalid file type. Must be 'history', 'ascii', or 'restart'")

    sourcePath = args.archDir

    os.chdir(sourcePath)
    return sourcePath


def parse_args():
    """
    The core function for parsing arguments. Arguments for fretransfer,
    userDef arguments, and frerun arguments are defined and parsed here.
    The userDef and frerun arguments are grabbed from configuration files,
    which are located in the same directory as the argFile temporary files.

    Parameters (0):
    - None

    Returns (1):
    - The arguments from fretransfer

    """

    parser = argparse.ArgumentParser(description="Fretransfer generates a FRE-style argFile with user-defined parameters and FRE-defined \nshell variables and then passes these newly formed '.args' files to FRE's output.stager")
   
    parser.register('action', 'extend', ExtendAction)

    if not os.path.exists(freDefArgCfg):
        raise FileNotFoundError("The configuration file for 'freDefs' arguments does not exist")

    with open(freDefArgCfg, 'r') as f:
        config_userDefs.read_file(f)

    add_argparse_arguments(config_userDefs, parser)

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format=logging_format)

    if args.actionSaveOn or args.actionCombineOn:
        if len(args.saveOptions) <= 4:
            raise ArgumentError("If combining or tarring files for batch jobs, Slurm save options must be added via -saveBatchOpts")

    if args.actionXferOn:
        if len(args.xferOptions) <= 4:
            raise ArgumentError("If using -transfer, Slurm transfer options must be added via -xferBatchOpts")

    return args


def submit_job(argFileLoc, batchString, special_case=[False, False], special_batch_locs=("", "")):
    """
    Calls output.stager via 'batch.scheduler.submit', which creates and submits
    a batch job via the Slurm scheduler. There are instances where tar files
    are not desired after a combine has taken place. This is deemed a 'special
    case'. If so, this function will execute a separately created output.stager
    batch job, which will then subsequently submit a separately created gcp
    batch job.

    Parameters (4):
    - argFileLoc: location of the .args file
    - batchString: String containing Slurm directives for the output.stager job
    - special_case: List of Booleans that denotes if un-tarred combined/uncombined files
                    will be transferred
    - special_batch_locs: Tuple of strings that references the location of the separately
                          created batch jobs
   
    Returns (0):
    - None

    """

    if special_case[0]:
        outputStager_batch_location = special_batch_locs[0]
        subprocess.call(["sbatch", outputStager_batch_location])
    elif special_case[1]:
        gcp_batch_location = special_batch_locs[1]
        subprocess.call(["sbatch", gcp_batch_location])
    else:
        output_stager_exec = shutil.which("output.stager")
        batch_scheduler_submit_exec = shutil.which("batch.scheduler.submit")
        subprocess.call([batch_scheduler_submit_exec, "--verbose", "-O", batchString.replace("(", "").replace(")", ""), output_stager_exec])
    

def write_special_jobs(args, argfile_obj):
    """
    Creates separate executable Slurm jobs for transferring un-tarred history, 
    restart, and ascii files.

    Parameters (2):
    - args: argparse object
    - argfile_obj: argFile object

    Returns (1):
    - Tuple containing the locations of the output.stager job file and the gcp
      job file.

    """

    batch_name_gcp = args.fileType[0] + "_gcp.batch"
    batch_name_outputStager = args.fileType[0] + "_outputStager.batch"
    header = "#!/bin/csh -fx\n"
    directive_string = ""

    batch_location = args.archDir + "/../"
    batch_location_outputStager = batch_location + batch_name_outputStager
    batch_location_gcp = batch_location + batch_name_gcp

    for option in args.saveOptions:
        directive_string += "#SBATCH --" + option + "\n"

    job_content_outputStager = header + directive_string + "\n" + "module load fre/bronx-16\n" \
                               + "alias outputStager `which output.stager`\n" \
                               + "alias sbatch `which sbatch`\n" \
                               + "outputStager " + argfile_obj.newFileLocation + "\n" \
                               + "sbatch " + batch_location_gcp

    with open(batch_location_outputStager, 'w') as f:
        f.write(job_content_outputStager)

    os.chmod(batch_location_outputStager, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH) #Equivalent to chmod 755

    directive_string = ""
    for option in args.xferOptions:
        directive_string += "#SBATCH --" + option + "\n"

    job_content_gcp = header + directive_string + "\n" + "alias gcp `which gcp`\n" \
                  + "gcp -r --create-dirs --verbose " + args.archDir + " gfdl:" \
                  + args.outputDirRemote

    with open(batch_location_gcp, 'w') as g:
        g.write(job_content_gcp)

    os.chmod(batch_location_gcp, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH) #Equivalent to chmod 755
    
    return (batch_location_outputStager, batch_location_gcp)
    

def main():
    """
    The meat of fretransfer. Creates an argFile object using a template and writes
    out a new .args file to the appropriate directory, given specific command-line
    arguments. If specified, batch jobs will also be submitted to the Slurm queue.

    Parameters (0):
    - None

    Returns (0):
    - None

    """

    args = parse_args()

    logging.info('Parsing userDef arguments')

    special_cases = [False, False]
    spec_batch_locs = ("", "")

    if args.paramCompressOn:
        args.paramCompressOn = 1
    else:
        args.paramCompressOn = 0
    
    if args.actionCombineOn:
        args.actionCombineOn = 1
    else:
        args.actionCombineOn = 0

    if args.actionSaveOn:
        args.actionSaveOn = 1
        args.paramArchiveOn = 1
    else:
        args.actionSaveOn = 0

    if args.actionXferOn:
        args.actionXferOn = 1
        if args.actionCombineOn == 1 and args.actionSaveOn == 0:
            args.actionXferOn = 0 #special case
            special_cases[0] = True
    else:
        args.actionXferOn = 0

    if args.paramCompressOn == 1 and args.actionSaveOn == 0:
        raise ArgumentError("You must specify the '-tar' argument when '-compress' is used!")
  
    argDict = {}
    for a in vars(args):
        argDict[a] = getattr(args, a)
    
    for ftype in args.fileType:
        sourcePath = get_sourcepath(args, ftype)

        A = argFile(ftype, args.archDir)

        # clean out argFiles from the working directory
        clean_dir(os.path.split(A.newFileLocation)[0], ['*.args*'])
        # copy the template file to the working directory

        tar_list = glob.glob(args.archDir + "/../*.tar")
        if (os.path.basename(args.archDir) + ".tar") in tar_list:
            special_cases[1] = True

        if special_cases[0] or special_cases[1]:
            spec_batch_locs = write_special_jobs(args, A)

        args.saveOptions.append("export=argFile=" + A.newFileLocation)
        args.xferOptions.append("export=argFile=" + A.newFileLocation)

        args.xferOptions = "( --" + " --".join(args.xferOptions) + " )"
        args.saveOptions = "( --" + " --".join(args.saveOptions) + " )"

        argDict["saveOptions"] = args.saveOptions
        argDict["xferOptions"] = args.xferOptions

        copy_file(A.templateLocation, A.newFileLocation)
        # write values in the argDict to the argFile
        write_file(A.newFileLocation, "w", **argDict)

        f = open(args.archDir + "/../" + os.path.basename(args.archDir) + ".ok", 'w')
        f.close()

        if args.submit:
            if (args.actionSaveOn == 0 and args.actionCombineOn == 1) or (special_cases[0] or special_cases[1]):
                submit_job(A.newFileLocation, args.saveOptions, special_case=special_cases, special_batch_locs=spec_batch_locs)

            elif args.actionSaveOn == 1:
                if args.actionCombineOn == 1:
                    if args.actionXferOn == 1:
                        submit_job(A.newFileLocation, args.saveOptions)
                    else:
                        submit_job(A.newFileLocation, args.saveOptions)
                else:
                    submit_job(A.newFileLocation, args.saveOptions)

            elif args.actionXferOn == 1: 
                submit_job(A.newFileLocation, args.xferOptions)
        
       
if __name__ == '__main__': 

    main()

