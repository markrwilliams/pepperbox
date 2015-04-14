#include <Python.h>


struct cpython_34c_state {
    PyObject *state;
};

static struct PyModuleDef cpython_34cmodule;


#define cpython_34c_state(o) ((struct cpython_34c_state *)PyModule_GetState(o))


static int
cpython_34c_clear(PyObject *m)
{
    Py_CLEAR(cpython_34c_state(m)->state);
    return 0;
}

static int
cpython_34c_traverse(PyObject *m, visitproc visit, void *arg)
{
    Py_VISIT(cpython_34c_state(m)->state);
    return 0;
}

static void
cpython_34c_free(void *m)
{
    cpython_34c_clear(m);
}



static PyObject *
cpython_34c_test_state(PyObject *self)
{
    PyObject *ret = cpython_34c_state((PyState_FindModule(&cpython_34cmodule)))->state;
    Py_INCREF(ret);
    return ret;
}


static PyMethodDef _functions[] = {
    {"test_state", (PyCFunction) cpython_34c_test_state, METH_NOARGS},
    {NULL, NULL}
};


static struct PyModuleDef cpython_34cmodule = {
   PyModuleDef_HEAD_INIT,
   "cpython_34c",
   NULL,
   sizeof(struct cpython_34c_state),
   _functions,
   NULL,
   cpython_34c_traverse,
   cpython_34c_clear,
   cpython_34c_free,
};


PyMODINIT_FUNC
PyInit_cpython_34c(void)
{
    const char module_constant[] = "cpython_34 extension module";
    const char state_constant[] = "cpython_34 extension module state";
    PyObject *m, *StringConstant, *StateStringConstant;
    m = PyModule_Create(&cpython_34cmodule);
    if (m == NULL)
        return m;

    StringConstant = PyUnicode_FromString(module_constant);
    Py_INCREF(StringConstant);
    PyModule_AddObject(m, "contents", StringConstant);

    struct cpython_34c_state *st = PyModule_GetState(m);
    StringConstant = PyUnicode_FromString(module_constant);
    StateStringConstant = PyUnicode_FromString(state_constant);
    Py_INCREF(StateStringConstant);
    st->state = StateStringConstant;

    return m;
}
