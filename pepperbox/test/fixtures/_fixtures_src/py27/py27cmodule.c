#include <Python.h>


PyMODINIT_FUNC
initpy27c(void)
{
    const char constant[] = "py27 extension module";
    PyObject *m, *StringConstant;
    m = Py_InitModule("py27c", NULL);
    if (m == NULL)
        return;
    StringConstant = PyString_FromString(constant);
    Py_INCREF(StringConstant);
    PyModule_AddObject(m, "contents", StringConstant);
}
