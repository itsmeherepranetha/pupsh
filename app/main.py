import sys
import os
import subprocess
import shlex
import readline
from typing import Callable, Optional


builtin_commands:dict[str,Callable[[str],None]]={}
_executables_cache:set[str]|None=None
last_appended_index:int=0
initial_history_length:int=0

# add to HISTFILE before exiting
def write_to_history_file()->None:
    histfile=os.environ.get("HISTFILE")
    if not histfile:
        return
    total=int(readline.get_current_history_length())  # type: ignore
    new_lines=int(total-initial_history_length)
    if new_lines>0:
        readline.append_history_file(new_lines,histfile)  # type: ignore

def exit_shell(input:str)->None:
    write_to_history_file()
    if input.strip().isdigit():
        sys.exit(int(input))   # exit with given status code
    else:
        sys.exit(0)  

def echo(input:str)->None:
    print(input)

def get_cwd(_:str)->None:
    print(os.getcwd())


def find_executable(cmd:str)->Optional[str]:
    # going to all directories and checking if the file exists and is accessible for execution
    path_dirs=os.environ.get("PATH","").split(os.pathsep)
    for directory in path_dirs:
        if not os.path.isdir(directory): # normally only directories are present in PATH, but just in case if someone has put a file in PATH, then ignore it
            continue
        full_path=os.path.join(directory,cmd)
        if os.path.isfile(full_path) and os.access(full_path,os.X_OK):
            return full_path
    return None

def typeOf(input:str)->None:
    # checking if its a bulitin command
    if input in builtin_commands:
        print(f"{input} is a shell builtin")
        return
    
    # checking if the input path exists and is an executable from the environment variables
    executable_path=find_executable(input)
    if executable_path:
        print(f"{input} is {executable_path}")
        return

    print(f"{input}: not found")

def change_directory(input:str)->None:
    if input=='~':
        input=os.path.expanduser("~") # standard notation for home dir , so gives absolute path for home , in every OS
    try:
        os.chdir(input)
    except OSError:
        print(f"cd: {input}: No such file or directory")

def get_all_executables()->set[str]:
    global _executables_cache
    if _executables_cache:
        return _executables_cache
    
    executables:set[str]=set()
    path_dirs=os.environ.get("PATH","").split(os.pathsep)
    for directory in path_dirs:
        try: # only if the directory is accessible, otherwise os.listdir() will raise PermissionError
            for filename in os.listdir(directory):
                full_path=os.path.join(directory,filename)
                if os.path.isfile(full_path) and os.access(full_path,os.X_OK):
                    executables.add(filename)
        except PermissionError:
            continue
    _executables_cache=executables
    return executables

def auto_completer(text:str,state:int)->Optional[str]:
    executables=get_all_executables()
    builtin_options=[cmd for cmd in builtin_commands if cmd.startswith(text)] # taking all the possible keys in builtin_commands
    executable_options=[exe for exe in executables if exe.startswith(text)] # taking all the possible executable commands , from filepaths in PATH
    options=builtin_options+executable_options # total options to choose from
    if state<len(options):
        return options[state]+" " # cursor appears after completion and an extra space
    return None

def parse_input(command:str)->list[str]:
    # using shlex to parse commands like a real shell would do
    lexer=shlex.shlex(command,posix=True) # posix=True tells to read the command like how Unix shell would read, if False then its like a normal parser
    lexer.whitespace_split=True # split on whitespaces , except inside single quotes, specified in next line
    # by default shlex treats single quotes as literal , does not touch it , and double quotes also , but allows escaping '\' when inside double quotes
    # supports backslash(\) as well when inside double quotes or single quotes
    tokens=list(lexer)
    return tokens

def extract_redirections(tokens:list[str])->tuple[list[str],Optional[str],str,Optional[str],str]:
    command:list[str]=[]
    stdout_target:Optional[str]=None
    stdout_mode:str="w" # by default
    stderr_target:Optional[str]=None
    stderr_mode:str="w" # by default

    i=0
    while i<len(tokens):
        token=tokens[i]
        if token in ['>',"1>"]: # file descriptor 1, for sending output to output file, write mode
            stdout_target=tokens[i+1]
            stdout_mode="w"
            i+=2
        elif token=="2>": # file descriptor 2, for sending errors to output file, write mode
            stderr_target=tokens[i+1]
            stderr_mode="w"
            i+=2
        elif token in [">>","1>>"]: # file descriptor 1, for sending output to output file, append mode
            stdout_target=tokens[i+1]
            stdout_mode="a"
            i+=2
        elif token=="2>>": # file descriptor 2, for sending errors to output file, append mode
            stderr_target=tokens[i+1]
            stderr_mode="a"
            i+=2
        else:
            command.append(token)
            i+=1

    return command,stdout_target,stdout_mode,stderr_target,stderr_mode

def get_history(input:str)->None:
    global last_appended_index
    args=input.strip().split()

    # to read from a file , and adding it to history
    if len(args)==2 and args[0]=="-r": # read the commands in the specified path , and them to history too
        file_path=args[1]
        try:
            readline.read_history_file(file_path)  # type: ignore
        except FileNotFoundError:
            print(f"history: {file_path}: No such file or directory")
        return
    
    # to write to a file, all the commands in the command history
    if len(args)==2 and args[0]=="-w":
        file_path=args[1]
        readline.write_history_file(file_path)  # type: ignore
        return
    
    # to append to a file, all the commands in the command history, since the last history -a
    if len(args)==2 and args[0]=="-a":
        file_path=args[1]
        total=int(readline.get_current_history_length()) # type: ignore
        with open(file_path,"a") as f:
            for i in range(last_appended_index+1,total+1):
                f.write(readline.get_history_item(i)+"\n")  # type: ignore
        last_appended_index=total
        return
    
    # default: show all
    n=100
    if len(args)==1 and args[0].isdigit():
        n=int(args[0])
    total=readline.get_current_history_length() # type: ignore
    startindex=max(total-n,0) # type: ignore
    for i in range(startindex+1,total+1): # type: ignore # 1-based indexing in get_history_item()
        print(f"    {i}  {readline.get_history_item(i)}") # type: ignore

def handle_command(command:str)->None:
    # parsing like how a shell would parse
    tokens=parse_input(command)
    # extracting any redirections for stdout,stderr , if any
    commandArr,stdout_target,stdout_mode,stderr_target,stderr_mode=extract_redirections(tokens)

    # if its a builtin command
    if commandArr[0] in builtin_commands:
        # temporarily redirect stdout and/or stderr, and then back to console after the operation
        if stdout_target and stderr_target:
            with open(stdout_target,stdout_mode) as stdout_file, open(stderr_target,stderr_mode) as stderr_file:
                old_stdout=sys.stdout
                old_stderr=sys.stderr
                sys.stdout=stdout_file
                sys.stderr=stderr_file
                builtin_commands[commandArr[0]](" ".join(commandArr[1:]))
                sys.stdout=old_stdout
                sys.stderr=old_stderr
        elif stdout_target:
            with open(stdout_target,stdout_mode) as stdout_file:
                old_stdout=sys.stdout
                sys.stdout=stdout_file
                builtin_commands[commandArr[0]](" ".join(commandArr[1:]))
                sys.stdout=old_stdout
        elif stderr_target:
            with open(stderr_target,stderr_mode) as stderr_file:
                old_stderr=sys.stderr
                sys.stderr=stderr_file
                builtin_commands[commandArr[0]](" ".join(commandArr[1:]))
                sys.stderr=old_stderr
        else:
            builtin_commands[commandArr[0]](" ".join(commandArr[1:]))
        return


    # if its an external command
    executable_path=find_executable(commandArr[0])
    if executable_path:
        # getting the execuatble and if needed the stdout_file and/or stderr_file for redirecting outputs and /or errors
        if stdout_target and stderr_target:
            with open(stdout_target,stdout_mode) as stdout_file, open(stderr_target,stderr_mode) as stderr_file:
                subprocess.run(commandArr,executable=executable_path,stdout=stdout_file,stderr=stderr_file)
        elif stdout_target:
            with open(stdout_target,stdout_mode) as stdout_file:
                subprocess.run(commandArr,executable=executable_path,stdout=stdout_file)
        elif stderr_target:
            with open(stderr_target,stderr_mode) as stderr_file:
                subprocess.run(commandArr,executable=executable_path,stderr=stderr_file)
        else:
            subprocess.run(commandArr,executable=executable_path)
        return

        
    print(f"{commandArr[0]}: command not found")

def _init_builtins()->None:
     builtin_commands.update({
        "exit":exit_shell,
        "echo":echo,
        "type":typeOf,
        "pwd":get_cwd,
        "cd":change_directory,
        "history":get_history
    })
     
def readline_config()->None:
    # for history to remember atmost the latest 1000 commands
    readline.set_history_length(1000) # type: ignore
    # for auto completion when pressed <TAB>('\t')
    readline.set_completer(auto_completer) # type: ignore
    readline.parse_and_bind("tab: complete") # type: ignore
    # to add to history manually , instead of readline default behaviour
    readline.set_auto_history(False) # type: ignore

def load_history()->None:
    global initial_history_length
    histfile=os.environ.get("HISTFILE")
    if histfile and os.path.isfile(histfile):
        readline.read_history_file(histfile)  # type: ignore
    initial_history_length=readline.get_current_history_length() # type: ignore


def main()->None:
    
    # initializing builtins
    _init_builtins()

    # readline config
    readline_config()

    # loading history into memory, if history file is specified in HISTFILE
    load_history()
    

    while(True):
        command=input("$ ")
        if command.strip():  # only add non-empty commands
            readline.add_history(command)   # type: ignore
        handle_command(command)



if __name__ == "__main__":
    main()