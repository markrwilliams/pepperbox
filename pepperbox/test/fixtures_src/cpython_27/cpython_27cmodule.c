#include <Python.h>


PyMODINIT_FUNC
initcpython_27c(void)
{
    const char constant[] = "cpython_27 extension module";
    PyObject *m, *StringConstant;
    m = Py_InitModule("cpython_27c", NULL);
    if (m == NULL)
        return;
    StringConstant = PyString_FromString(constant);
    Py_INCREF(StringConstant);
    PyModule_AddObject(m, "contents", StringConstant);
}
