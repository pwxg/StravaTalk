"""
Streamlit interface for StravaTalk.
"""

import streamlit as st
from dotenv import load_dotenv
import pandas as pd
import traceback

from atomic_agents.lib.components.agent_memory import AgentMemory
from orchestrator import initialize_agents, process_query
from visualization import create_visualization, display_visualization, validate_chart_inputs
from agents.classify_agent import QueryType
from utils.debug_utils import (
    setup_debug_mode, 
    show_debug_header, 
    show_data_debug, 
    show_chart_debug, 
    show_error_debug,
    debug_visualization,
    is_debug_mode
)


def create_interface():
    """Create the Streamlit interface for StravaTalk."""
    st.set_page_config(page_title="StravaTalk", page_icon="🏃‍♂️", layout="centered", initial_sidebar_state="collapsed")  # Configure Streamlit page
    
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    
    debug_mode = setup_debug_mode()
    
    if debug_mode:
        st.title("StravaTalk 🏃‍♂️ 🐛")
        show_debug_header()
    else:
        st.title("StravaTalk 🏃‍♂️")
        
    load_dotenv()

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "text": "Welcome to the Strava Data Assistant! I can help you analyze your Strava activities. How can I assist you today?",
            }
        ]

    if "shared_memory" not in st.session_state:
        st.session_state.shared_memory = AgentMemory()

    if "agents" not in st.session_state:
        st.session_state.agents = initialize_agents(st.session_state.shared_memory)

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["text"])

            if st.session_state.is_processing:
                continue

            if (
                message["role"] == "assistant"
                and "chart_data" in message
                and "chart_info" in message
            ):
                try:
                    data = message["chart_data"]
                    if isinstance(data, list):
                        data = pd.DataFrame(data)

                    chart_info = message["chart_info"]
                    
                    if is_debug_mode():
                        debug_visualization(data, chart_info, st)
                    
                    is_valid, valid_y_columns, error_message = validate_chart_inputs(
                        data, chart_info["x_column"], chart_info["y_columns"]
                    )
                    
                    if not is_valid:
                        st.warning(error_message)
                        continue
                    
                    chart = create_visualization(
                        data, 
                        chart_info["x_column"], 
                        valid_y_columns, 
                        chart_info.get("chart_type", "line")
                    )
                    display_visualization(chart)
                    
                except Exception as e:
                    st.error(f"Error displaying visualization: {str(e)}")
                    if is_debug_mode():
                        show_error_debug(e, data, chart_info, st)

    if prompt := st.chat_input("Ask me anything about your Strava activities..."):
        handle_query(prompt)


def handle_query(user_query):
    """Process a user query and update the interface."""
    if not user_query:
        return

    try:
        st.session_state.is_processing = True
        
        st.session_state.chat_history.append({"role": "user", "text": user_query})

        with st.chat_message("user"):
            st.markdown(user_query)

        classify_agent, sql_agent, response_agent = st.session_state.agents

        with st.status("Processing your query...", expanded=False) as status:
            result = process_query(
                classify_agent, sql_agent, response_agent, user_query
            )

            classification = result["classification"]
            status.write(f"Query type: {classification.query_type}")

            if classification.query_type in [QueryType.SQL, QueryType.VIZ]:
                if result.get("sql_query"):
                    status.write("SQL Query:")
                    status.code(result["sql_query"], language="sql")

                if result["success"]:
                    if result.get("data") is not None:
                        status.write(f"Query returned {len(result['data'])} rows")

                        if is_debug_mode():
                            show_data_debug(result["data"], status)
                            if result.get("chart_info"):
                                show_chart_debug(result["chart_info"], status)

                    status.update(
                        label="Query processed successfully!", state="complete"
                    )
                else:
                    status.update(label="Error executing query", state="error")
            else:
                status.update(label="Query processed", state="complete")

        assistant_message = {
            "role": "assistant",
            "text": result["response_text"],
            "sql_query": result.get("sql_query"),
        }

        if (
            result["chart_info"]
            and result["data"] is not None
            and not result["data"].empty
        ):
            chart_info = result["chart_info"]
            x_column = chart_info["x_column"]
            y_columns = chart_info["y_columns"]
            chart_type = chart_info.get("chart_type", "line")

            is_valid, valid_y_columns, _ = validate_chart_inputs(result["data"], x_column, y_columns)
            
            if is_valid:
                assistant_message["chart_data"] = result["data"].to_dict("records")
                assistant_message["chart_info"] = {
                    "x_column": x_column,
                    "y_columns": valid_y_columns,
                    "chart_type": chart_type,
                }

                if "date" in x_column.lower() or "time" in x_column.lower():
                    try:
                        result["data"][x_column] = pd.to_datetime(
                            result["data"][x_column]
                        )
                    except:
                        pass

        st.session_state.chat_history.append(assistant_message)
        
        st.session_state.is_processing = False

        with st.chat_message("assistant"):
            st.markdown(result["response_text"])

            if "chart_data" in assistant_message and "chart_info" in assistant_message:
                try:
                    data = pd.DataFrame(assistant_message["chart_data"])

                    chart = create_visualization(
                        data,
                        assistant_message["chart_info"]["x_column"],
                        assistant_message["chart_info"]["y_columns"],
                        assistant_message["chart_info"].get("chart_type", "line"),
                    )
                    display_visualization(chart)
                except Exception as e:
                    st.error(f"Error displaying visualization: {str(e)}")
                    if is_debug_mode():
                        show_error_debug(e, data, assistant_message["chart_info"], st)

    except Exception as e:
        error_message = f"Error: {str(e)}"
        st.session_state.chat_history.append(
            {"role": "assistant", "text": error_message}
        )

        with st.chat_message("assistant"):
            st.error(error_message)

        if is_debug_mode():
            st.error(traceback.format_exc())
        
    finally:
        st.session_state.is_processing = False


def main():
    create_interface()


if __name__ == "__main__":
    main()
