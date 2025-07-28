import inspect
import os
import tempfile
from contextlib import contextmanager
from functools import wraps
from typing import TypeVar, Optional, Callable, List, Literal, Any, Generator

import pandas as pd
import streamlit as st
from streamlit_ace import st_ace
from streamlit_extras.stylable_container import stylable_container

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


def init_state_with_callable(name: str, func: Callable[[], T]) -> T:
    """
    If 'name' is not already in session state, initialise it to the result of calling 'func'. Return its resulting value in the session.
    """
    if name not in st.session_state:
        st.session_state[name] = func()
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

        def init_with_callable(initialiser: Callable[[], T]) -> T:
            """
            If the current session_state value is not initialised, initialise it by calling the function passed in.
            Either way return the now current value of the session state.
            """
            if self.name not in st.session_state:
                set_state(self.name, initialiser())
            return get_state(self.name)

        def clear():
            """
            Set the session_state value to None. If the value is non-None prior to clearing, then the cleanup function
            will be called before clearing.
            """
            safe_call(self.cleanup_func)
            set_state(self.name, None)


        def delete():
            """
            Delete the session_state value. If the value is non-None prior to deleting, then the cleanup function
            will be called before deleting.
            """
            safe_call(self.cleanup_func)
            del_state(self.name)

        def get(default_val: T | None = None) -> T:
            """
            Get the current session_state value.
            """
            return get_state(self.name, default_val)

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
        wrapper.init_with_callable = init_with_callable
        wrapper.clear = clear
        wrapper.delete = delete
        wrapper.get = get
        wrapper.safe_call = safe_call
        wrapper.call = call
        wrapper.history = history
        wrapper.session_key = self.name
        return wrapper


def st_stateful(widget_func, prop, obj, post_change: Callable = None, change_args: tuple[Any, ...] = None,
                change_kwargs: dict[str, Any] = None, **kwargs):
    """
    Given a streamlit widget function, a property name and a reference to a SessionObject value on which the property
    value belongs, create a stateful widget that will store the value of the widget in the SessionObject property, and
    set itself to the value of the property even between page switches, by using an explicit session state property for
    the widget.

    :param widget_func: The streamlit widget function to use (e.g. st.checkbox, st.selectbox, etc.)
    :param prop: The name of a property on an object that is stored using SesssionObject
    :param obj: The object with the above property (that is stored using SessionObject)
    :param kwargs: The keyword arguments to pass to the widget function

    :param post_change: A function to run after the widget value has changed
    :param change_args: The arguments to pass to the post_change function
    :param change_kwargs: The keyword arguments to pass to the post_change function

    NOTE:
      1. on_change, value and index parameters of the widget function are set by this function and should therefore not be passed in kwargs.
      2. You can set the label of your widget by passing a 'label' parameter in kwargs, or as the first argument in args.
      3. The default session state key is a combination of the object name, the property name and the widget function name, but you can pass a key parameter in kwargs to override this.

    Usage example:
        ```
        @SessionObject("my_session_object")
        def session_user_defined(value: UserDefined) -> UserDefined:
            return value

        # initialise if necessary
        session_user_defined.init(UserDefined())

        # get current value of the session object
        current_value = session_user_defined.get()

        # create a stateful checkbox widget that will store its value in the example 'enabled' property of the UserDefined object
        current_value = st_stateful(st.checkbox, "enabled", current_value, label="Enable feature")
        ```

    Then you can either access the value using current_value.enabled, or by assigning the result of the st_stateful call

    TODO: can all the default stuff be done by setting the session state value when None?
    """

    session_state_key = kwargs.pop("key", f"{type(obj).__name__}_{prop}_{widget_func.__name__}")

    def store_prop():
        """
        Function sets the value of the SessionObject's property to the value of the widget.
        This function will run on the on_change event of the widget before refresh
        """
        current_val = st.session_state[session_state_key]
        setattr(obj, prop, current_val)

        if post_change is not None:
            post_change(current_val, *(change_args or ()), **(change_kwargs or {}))

    # if the args list is empty and no label is specified in kwargs, use the property name as the label
    if "label" not in kwargs:
        kwargs["label"] = prop

    # if the widget is a selectbox or radio (i.e. a widget requiring the 'options' param), try to set the index of the widget (i.e. default value) to the index of the current value of the property in question
    if widget_func.__name__ in {"selectbox", "radio"}:
        try:
            kwargs["index"] = kwargs.get("options").index(getattr(obj, prop))
        except ValueError:
            # if the current value of the property is not in the options list, set the index to 0 and update the object's property to that value
            if kwargs.get("options", []):
                kwargs["index"] = 0
                setattr(obj, prop, kwargs.get("options")[0])
    # if the widget is a segmented control
    elif widget_func.__name__ in {"segmented_control"}:
        kwargs["default"] = getattr(obj, prop)
    # otherwise, set the value parameter of the widget directly to the value of the property of the SessionObject
    else:
        kwargs["value"] = getattr(obj, prop)

    # returns the value of the widget, and sets the value of the widget to the value of the property of the SessionObject
    return widget_func(key=session_state_key, on_change=store_prop, **kwargs)


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
        st.info(message, icon=":material/info:")
    elif status_type == "warn":
        st.warning(message, icon=":material/️warning:")
    elif status_type == "error":
        st.error(message, icon=":material/error:")
    elif status_type == "success":
        st.success(message, icon=":material/check:")


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

def toast_success(msg: str):
    """ Display a success toast message. """
    st.toast(msg, icon=":material/check:")


def toast_warning(msg: str):
    """ Display a warning toast message. """
    st.toast(msg, icon=":material/warning:")


def toast_error(msg: str):
    """ Display an error toast message. """
    st.toast(msg, icon=":material/error:")


def toast_refreshed():
    """ Display a success toast message for a successful refresh. """
    toast_success("Refreshed")


def color_text(text: str, color: str) -> str:
    """ Color the text with the given color (requires st.markdown to display) """
    return f":{color}[{text}]"


def primary_text(text: str) -> str:
    """ Color the text with the primary color of the current streamlit theme """
    return color_text(text, "primary")


def st_widget_caption(text: str):
    """
    Hack to create a caption in the styling of other widget labels, instead of the normal caption text.
    This means you can caption whole sets of widgets with a single caption in the position you desire
    instead of directly above only one widget.
    """
    st.caption(f'<p style="color:rgb(49, 51, 63);">{text}</p>', unsafe_allow_html=True)


def st_multiselect_with_additional_controls(init_val: list = None,
                                            control_gap: Literal["small", "medium", "large"] = "small",
                                            picker_dialog: Callable[[str], list] = None,
                                            **multiselect_kwargs):
    """
    A multiselect widget with additional controls to select all or deselect all options.
    Keywords args are parsed to the underlying multiselect. In particular, you should
    specify:
    - label: The label for the multiselect
    - key: The key for the multiselect (used to built the key for the toggle buttons too)
    - options: The list of options for the multiselect
    Any additional args are passed through.
    """
    label = multiselect_kwargs.pop("label", "Select options")
    key = multiselect_kwargs.pop("key", label)
    options = multiselect_kwargs.pop("options", [])

    if init_val and key not in st.session_state:
        st.session_state[key] = init_val

    def select_all():
        st.session_state[key] = options

    def deselect_all():
        st.session_state[key] = []

    st_widget_caption(label)
    control_cols = st.columns(3 if picker_dialog else 2, gap=control_gap)
    control_cols[0].button("All", on_click=select_all, icon=":material/select_all:", use_container_width=True, key=f"{key}_select_all", help="Select all options")
    control_cols[1].button("None", on_click=deselect_all, icon=":material/deselect:", use_container_width=True, key=f"{key}_deselect_all", help="Deselect all options")
    if picker_dialog:
        if control_cols[2].button("Picker", icon=":material/gesture_select:", use_container_width=True, key=f"{key}_picker_dialog", help="Batch select options in a dialog overlay window."):
            picker_dialog(key)
    return st.multiselect(label, options=options, key=key, label_visibility="collapsed", **multiselect_kwargs)


@contextmanager
def st_container_right_aligned(key: str):
    """
    Context manager to create a container with right-aligned text.
    """
    with stylable_container(key=key, css_styles="""
    {
        text-align: right;
    }
    """):
        yield


@st.dialog("Confirmation required")
def st_dialog_confirmation(on_confirm: Callable,
                           streamlit_write_func: Callable = None,
                           action_loading_text: str = "Loading...",
                           cancel_text: str = "Cancel",
                           confirm_text: str = "Confirm",
                           on_confirm_args: tuple | None = None,
                           on_config_kwargs: dict | None = None):
    """
    Display a dialog modal to confirm an action before proceeding.
    :param on_confirm: The function to call when the user clicks the confirm button
    :param streamlit_write_func: The function to call to display any content in the modal using stremalit widgets
    :param action_loading_text: The text to display in the spinner while the action is being performed
    :param cancel_text: The text to display on the cancel button
    :param confirm_text: The text to display on the confirm button
    :param on_confirm_args: The arguments to pass to the on_confirm function
    :param on_config_kwargs: The keyword arguments to pass to the on_confirm function
    """
    if streamlit_write_func is not None:
        streamlit_write_func()
    else:
        st.write("Are you sure?")
    cancel_col, confirm_col = st.columns(2)
    if cancel_col.button(cancel_text, use_container_width=True):
        st.rerun()
    if confirm_col.button(confirm_text, type="primary", use_container_width=True):
        with st.spinner(action_loading_text):
            args = on_confirm_args or ()
            kwargs = on_config_kwargs or {}
            on_confirm(*args, **kwargs)
        st.rerun()


def st_multiselect_accepts_new(input_widget_func, label: str,
                               session_object_list_prop: list[Any],
                               key: str = None,
                               keep_duplicates: bool = False,
                               column_layout: list[int | float] | None = None,
                               input_widget_kwargs: dict[str, Any] = None,
                               multiselect_widget_kwargs: dict[str, Any] = None) -> list[str]:
    """
    A widget made from three streamlit components to basically allow a user to input new values into a multiselect-like
    widget. The user enters new values in the passed input_widget_func (e.g. st.text_input), then
    clicks the "+" button. The new value is added to the existing values in the segemented control widget.
    Existing values can be removed by clicking them in the segmented control

    The output of this function is the final selection of values.

    The session_object_list_prop is a list that will be modified in place to store the selected values,
    so it should be a list that is a field on a streamlit SessionObject.

    You can pass kwargs to the input widget using a dict as input_widget_kwargs, and to the multiselect widget using
    multiselect_widget_kwargs.

    """
    if not key:
        key = label
    if not column_layout:
        column_layout = [0.35, 0.05, 0.6]

    add_new_key = f"{key}_add_new"
    button_key = f"{add_new_key}_button"

    # Get the existing values in the list
    def get_existing():
        return session_object_list_prop

    # Add to the list when people click on the add button after entering a new value
    def update_existing():
        new_val = st.session_state[add_new_key] if add_new_key in st.session_state else None
        if new_val is not None:
            current = get_existing()
            if keep_duplicates or new_val not in current:
                current.append(new_val)

    # Delete from the list when people click on the segmented control
    def delete_existing():
        if key in st.session_state:
            existing = st.session_state[key]
            if current := get_existing():
                current.remove(existing)

    input_col, button_col, selected_col = st.columns(column_layout, gap="small", vertical_alignment="bottom")
    with input_col:
        input_widget_func(label=f"Add {label}", key=add_new_key, **(input_widget_kwargs or {}))
    with button_col:
        st.button(":material/add:", key=button_key, on_click=update_existing, use_container_width=True)
    with selected_col:
        existing_values = get_existing()
        if existing_values:
            st.segmented_control(label, selection_mode="single",
                                 on_change=delete_existing,
                                 options=existing_values, key=key, **(multiselect_widget_kwargs or {}))
        else:
            st.warning("No values selected")

    return existing_values


def st_grid(items: list[T], columns: int, separate_rows=False, **kwargs) -> Generator[T, None, None]:
    """
    Display a grid of items in columns
    Usage:
    ```
    for item in st_grid(items, columns):
        st.write(item)   # this will be scoped to the current grid cell
    ```
    """
    grid = st.columns(columns, **kwargs)
    col = 0
    for item in items:
        with grid[col]:
            yield item
            col = (col + 1) % columns
        if separate_rows and col % columns == 0:
            grid = st.columns(columns, **kwargs)

