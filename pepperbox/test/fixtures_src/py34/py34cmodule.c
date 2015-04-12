#include <Python.h>


struct py34c_state {
    PyObject *state;
};

static struct PyModuleDef py34cmodule;


#define py34c_state(o) ((struct py34c_state *)PyModule_GetState(o))


static int
py34c_clear(PyObject *m)
{
    Py_CLEAR(py34c_state(m)->state);
    return 0;
}

static int
py34c_traverse(PyObject *m, visitproc visit, void *arg)
{
    Py_VISIT(py34c_state(m)->state);
    return 0;
}

static void
py34c_free(void *m)
{
    py34c_clear(m);
}



static PyObject *
py34c_test_state(PyObject *self)
{
    PyObject *ret = py34c_state((PyState_FindModule(&py34cmodule)))->state;
    Py_INCREF(ret);
    return ret;
}


static PyMethodDef _functions[] = {
    {"test_state", (PyCFunction) py34c_test_state, METH_NOARGS},
    {NULL, NULL}
};


static struct PyModuleDef py34cmodule = {
   PyModuleDef_HEAD_INIT,
   "py34c",
   NULL,
   sizeof(struct py34c_state),
   _functions,
   NULL,
   py34c_traverse,
   py34c_clear,
   py34c_free,
};


PyMODINIT_FUNC
PyInit_py34c(void)
{
    const char module_constant[] = "py34 extension module";
    const char state_constant[] = "py34 extension module state";
    PyObject *m, *StringConstant, *StateStringConstant;
    m = PyModule_Create(&py34cmodule);
    if (m == NULL)
        return m;

    StringConstant = PyUnicode_FromString(module_constant);
    Py_INCREF(StringConstant);
    PyModule_AddObject(m, "contents", StringConstant);

    struct py34c_state *st = PyModule_GetState(m);
    StringConstant = PyUnicode_FromString(module_constant);
    StateStringConstant = PyUnicode_FromString(state_constant);
    Py_INCREF(StateStringConstant);
    st->state = StateStringConstant;

    return m;
}
