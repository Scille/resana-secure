// Resana Secure Copyright (c) 2021 Scille SAS

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <wchar.h>

int main(int argc, char *argv[])
{
    wchar_t** _argv = PyMem_Malloc(sizeof(wchar_t*)*argc);
    for (int i = 0; i < argc; i++) {
      wchar_t* arg = Py_DecodeLocale(argv[i], NULL);
        if (arg == NULL) {
            fprintf(stderr, "Fatal error: cannot decode argv\n");
            exit(1);
        }
      _argv[i] = arg;
    }

    Py_SetProgramName(_argv[0]);  /* optional but recommended */
    Py_Initialize();
    PySys_SetArgv(argc, _argv);

    PyRun_SimpleString(
        "from resana_secure.cli import run_cli\n"
        "run_cli()\n"
    );

    for (int i = 0; i < argc; i++) {
        PyMem_RawFree(_argv[i]);
    }
    PyMem_RawFree(_argv);

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }
    return 0;
}
