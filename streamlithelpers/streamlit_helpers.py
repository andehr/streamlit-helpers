import inspect
import os
import tempfile
from functools import wraps
from typing import TypeVar, Optional, Callable, List, Literal, Any

import pandas as pd
import streamlit as st
from streamlit_ace import st_ace

T = TypeVar("T")
StatusType = Literal["info", "warn", "error", "success"]


###################################
# Manage session state
###################################
def init_state(name: str, value: T) -> T:
    """
    If 'name' is not already in session state, initialise it to 'value'. Return its resulting value in the session.
    """
    if name not in st.session_state:
        st.session_state[name] = value
    return st.session_state[name]


def set_state(name: str, value: T) -> T:
    """
    Set 'name' in the session state to 'value' and return value.
    """
    st.session_state[name] = value
    return value


def del_state(name: str):
    """
    Delete 'name' from the session state.
    """
    if name in st.session_state:
        del st.session_state[name]


def get_state(name: str, default_val: Optional[T] = None) -> T:
    """
    Get the value of 'name' in the session state or None if not present.
    """
    return st.session_state[name] if name in st.session_state else default_val


class SessionObject:
    """
    Decorator to be used on functions whose return values should be stored in session_state.
    Session state contains key-value pairs. The function's result is the value,
    and the name you specify to the decorator is the key. E.g:

    @SessionObject("my_data", history_size=10)
    def my_data(arg1, arg2):
        # get the data

    Then whenever get_data(arg1, arg2) is called, its result is stored in session_state["my_data"],
    where anything else can then grab it. The data is still returned, so if the caller
    wants to use the result of get_data() straightaway they still can.

    If history_size > 0, then the last *history_size* values for my_data will be recorded and available using my_data.history()

    Extra methods are also added to the function for easy session_state manipulation:

        get(): gets the current value from the session_state from the last time the function was called.
        clear(): sets the current session_state value to None (the initial state)
        init(): checks whether there's a value in the session_state other than None, if not it sets the value
                by calling the decorated function and using its return value. It then returns the current
                session_state value.
        history() : set or get the history of values (if history_size is set to > 0).
        safe_call() : calls a specified function on the current session state value, if that value is not None.
        call()   : calls a specified function on the current session state value, even if that value is None or non-existent

    The functions are attached directly to the decorated function. So you call them directly on the function name. E.g
    for the above example: my_data.get(), my_data.clear(), my_data.init(). This means all session state manipulation
    can be done without passing around string names all the time.
    """

    def __init__(self, name: str, history_size: int = 0, cleanup_func: Callable[[T], Any] = lambda t: None):
        """
        Decorator parameters.
        :param name: Required. This will be the name of the object in the session state.
        :param history_size: Optional. If N > 0, then N previous values of the the session state will be tracked.
        :param cleanup_func: Optional. This function is called before clear() removes the value from the session state (if not None)
        """
        self.name = name
        self.history_size = history_size
        self.cleanup_func = cleanup_func

    def __call__(self, func: Callable[..., T]) -> T:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            set_state(self.name, result)
            if self.history_size > 0:
                _update_history(result)
            return result

        def _update_history(result):
            items = history()
            if result not in items:
                if len(items) >= self.history_size:
                    items.pop()
                history([result] + items)

        def init(*args, **kwargs):
            """
            If the current session_state value is None, initialise it by calling the decorated function, passing
            through any args or kwargs given to this function.
            Then return the current session_state value.
            """
            if self.name not in st.session_state:
                set_state(self.name, func(*args, **kwargs))
            return get_state(self.name)

        def clear():
            """
            Set the session_state value to None. If the value is non-None prior to clearing, then the cleanup function
            will be called before clearing.
            """
            safe_call(self.cleanup_func)
            set_state(self.name, None)

        def get() -> T:
            """
            Get the current session_state value.
            """
            return get_state(self.name, None)

        def safe_call(f: Callable[[T], Any], default_value: Any = None) -> Any:
            """
            If the current session state is not None, then return the result of f(current_state).
            Otherwise, return default value.
            """
            if (state := get_state(self.name, None)) is not None:
                return f(state)
            return default_value

        def call(f: Callable[[Optional[T]], Any]) -> Any:
            """
            Return the result of f(current_state). Callable should be prepared to accept None. Alternatively
            use safe_call().
            """
            return f(get_state(self.name, None))

        def history(val: Optional[List[T]] = None) -> List[T]:
            """
            Get/set history state. If val is None, then the session state history
            is just returned. Otherwise, the history is set to val and returned.
            """
            history_name = f"{self.name}_history"
            if val is None:
                return get_state(history_name, [])
            else:
                return set_state(history_name, val)

        # Attach the helper functions to the decorated function
        wrapper.init = init
        wrapper.clear = clear
        wrapper.get = get
        wrapper.safe_call = safe_call
        wrapper.call = call
        wrapper.history = history
        return wrapper

###################################
# Widget helpers
###################################


@st.cache_data(ttl="1hour")
def df_to_csv_cached(df: pd.DataFrame) -> bytes:
    """
    Convert dataframe to CSV string ready for a download button, cache result for 1 hour
    """
    return df.to_csv().encode("utf-8")


def st_dataframe_with_download(df: pd.DataFrame, filename: str = None, **kwargs):
    """
    Display a dataframe with an accompanying download button to download the dataframe as a CSV.
    """
    csv = df_to_csv_cached(df)
    st.dataframe(df, **kwargs)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=filename,
        mime='text/csv')


def st_download_button_via_file(generate_label: str,
                                download_label: str,
                                save_func: Callable[[str], None],
                                filename: str = None,
                                use_container_width: bool = False):
    """
    Draw a button which when clicked actually just saves something to file using the save_func,
    and sets up a new download button loaded with the contents of the file.
    Useful if you only want to generate the download button contents when specifically
    requested by the user, or if using a library that can only save to file (e.g. not raw string)
    Since Streamlit's download button currently (as of v1.23) requires the contents in memory.
    """
    if st.button(generate_label, use_container_width=use_container_width):
        # Create temp file for backup
        fd, path = tempfile.mkstemp(dir=os.getcwd())
        with st.spinner("Saving..."):
            # Use save function to write contents to temp file
            save_func(path)
            # Read the temporary file into memory as stream of bytes ready for download button
            with os.fdopen(fd, 'rb') as save_file:
                file_bytes = save_file.read()
        # delete temporary file
        os.remove(path)
        # Create download button which stores the file bytes
        st.download_button(
            label=download_label,
            data=file_bytes,
            file_name=filename,
            use_container_width=use_container_width)


def st_status(message: str, status_type: StatusType):
    """
    Place display widget containing the given message. Widget should be appropriate to the status type (including an icon).
    """
    if status_type not in {"info", "warn", "error", "success"}:
        raise ValueError(f"Invalid status type: {status_type}")
    if status_type == "info":
        st.info(message, icon="ℹ️")
    elif status_type == "warn":
        st.warning(message, icon="⚠️")
    elif status_type == "error":
        st.error(message, icon="❌")
    elif status_type == "success":
        st.success(message, icon="✅")


def st_source_code(obj):
    """
    Display the source code of a given python object.
    """
    st.code(inspect.getsource(obj), language="python")


def st_code_editor(key: str, value=None, placeholder: str = "", **kwargs) -> str:
    """
    Place a code editor in the app.
    :param value: Initial code filling
    :param key: A key name for storing result in session cache
    :param placeholder: A placeholder to initialise return value.
    :param kwargs: Any keyword arg supported by st_ace (underlying library)
    :return: The editor contents.
    """
    init_state(key, value if value is not None else "")
    code = st_ace(value=get_state(key), key=key, placeholder=placeholder, **kwargs)
    return code if code is not None else placeholder
