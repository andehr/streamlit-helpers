# Install

`pip install streamlithelpers`

# Session state helpers

## Basic

Helper functions like `set_state(key, value)`, `get_state(key)` and `init_state(key, value)` 
avoid repetitive if-statement and None checking patterns.

## Advanced

The `SessionObject` decorator makes it easier to work with Python identifiers as containers
of session state instead of passing around String keys to `get_state()` or `set_state()`.

E.g. the simplest usage might be:

```python
@SessionObject("result")
def result(val):
    return val
```

Then:

1. Calling `result(2)` would put `2` in the session state under the key `result`. 
2. You could get the current value by calling `result.get()`, or 
3. Set it to something else like `result(3)`. Or,
4. Set the state value to `None` with `result.clear()`.
5. Or `result.init(2)` which calls `result(2)` only if there isn't a value in the session state already.

But the `SessionObject` provides other utilities like cleanup functions and history if configured. 
And the body of the function can do any processing on the inputs before returning the final 
session state value.

```python
@SessionObject("result", history_size=10, cleanup_func=cleanup)
def result(val):
    # any amount of processing before final val
    return val
```

Here the last `10` results of calls to `result()` are stored, and can be acquired via `result.history()`.
And `cleanup(result.get())` is run first when `result.clear()` is called if `result.get()` is not None.

# Widget helpers

Some functions are provided which display one or more streamlit widgets to support common workflows.
They all start with `st_`.

## Downloading
Currently, if you make a download button with Streamlit, the contents must already be in memory, 
so below are some helpers for dealing with that.

`st_dataframe_with_download()` : displays a st.dataframe() widget with an accompanying download 
button which downloads a CSV of the dataframe - the button is primed with the full contents of the
CSV for you. The dataframe to string conversion is cached for an hour.

`st_download_button_via_file()` : displays a button which on click performs a save function you specify
to a temporary file, then makes a download button that is primed with the contents of that temp file.
Useful for big files you only want to generate when the user asks for it, especially if the save
function relies on a library function that writes to file.

## Display

`st_status(message, type)` : displays a status message in a colour appropriate to a specified type (error/warn/info/success)
with an appropriate icon.

`st_source_code(obj)` : the streamlit widget `st.code()` will display only a String literal representing some code. This function
takes any Python object, finds its source code via Python's `inspect.getsource()` and displays that code.

`st_code_editor` : display a code editor backed by `st_ace` library, but doing some annoying defaults,
like making sure initial state is empty string not `None`, and that state is initialised.
