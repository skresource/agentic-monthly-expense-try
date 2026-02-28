import streamlit as st
import pandas as pd
import google.generativeai as genai
from datetime import datetime
import os
import json
from excel_manager import update_excel, ExpenseData
from analysis_tool import (
    load_expense_data, get_months_in_data, get_monthly_summary,
    compare_months, create_monthly_pie_chart, create_comparison_chart,
    generate_monthly_report, generate_comparison_report, get_quick_stats
)
from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv()

# --- CONFIGURATION ---
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
print("geminiKey-", GEMINI_API_KEY[:5])
genai.configure(api_key=GEMINI_API_KEY)

# --- GOOGLE GEMINI EXTRACTION LOGIC ---
def extract_expense_details(user_input):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    # Prompting the model to return ONLY clean JSON
    prompt = f"""
    Extract expense details from this text: "{user_input}"
    Return a JSON object with these exact keys:
    - amount (number, extract numeric value, ignore currency symbols like /-, Rs., ₹)
    - subject (string, who received the money and on what purpose)
    - month (string, the month mentioned in the text if any. Look for month names like January, February, March, April, May, June, July, August, September, October, November, December or abbreviations. If month is mentioned (e.g., "for March", "advance for next month"), extract it. If not mentioned, return empty string "")
    - remarks (string, extract any additional notes/comments. Look for patterns like "Remarks:", "Note:", "Additional:", "Due:", "Status:" etc.)
    
    Current Month: {datetime.now().strftime("%B")}
    Return ONLY the JSON. No conversational text.
    Example 1: {{"amount": 200, "subject": "English teacher tuition", "month": "March", "remarks": ""}}
    Example 2: {{"amount": 500, "subject": "electricity bill", "month": "", "remarks": "Due payment"}}
    Example 3: {{"amount": 1500, "subject": "school fees", "month": "April", "remarks": "Advance payment"}}
    """
    
    response = model.generate_content(prompt)
    # Cleaning the response text to ensure it's valid JSON
    clean_json = response.text.strip().replace('```json', '').replace('```', '')
    data = json.loads(clean_json)
    
    # Ensure all required fields have default values
    if 'remarks' not in data:
        data['remarks'] = ""
    if 'month' not in data or data['month'].strip() == "":
        data['month'] = ""  # Keep blank if not mentioned, will use current month as fallback
    
    return data


def analyze_duplicate_clarification(user_input, pending_duplicate):
    """
    Use LLM to intelligently analyze if user is clarifying a duplicate 
    and extract the reason/context to add to remarks
    """
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    pending_str = json.dumps(pending_duplicate, indent=2)
    
    prompt = f"""
    User previously tried to add this expense (MARKED AS DUPLICATE):
    {pending_str}
    
    User just replied: "{user_input}"
    
    Analyze if the user is saying this is NOT a duplicate and they want to add it anyway.
    DO NOT ask for clarification, just analyze the intent.
    
    Return a JSON object with these exact keys:
    - is_clarification (boolean: true if user is saying it's not a duplicate/wants to add it, false if they want to skip)
    - remarks_addition (string: brief natural text to add to remarks explaining why this is not a duplicate. Empty string if not a clarification)
    - confidence (string: "high", "medium", or "low")
    
    Examples of responses:
    User says "no this is advance payment" → {{"is_clarification": true, "remarks_addition": "Advance payment for next month", "confidence": "high"}}
    User says "no I paid from different account" → {{"is_clarification": true, "remarks_addition": "Paid from different account", "confidence": "high"}}
    User says "booking amount" → {{"is_clarification": true, "remarks_addition": "Booking amount", "confidence": "high"}}
    User says "yes skip it" → {{"is_clarification": false, "remarks_addition": "", "confidence": "high"}}
    User says "ok" (ambiguous) → {{"is_clarification": false, "remarks_addition": "", "confidence": "low"}}
    
    Return ONLY the JSON. No conversational text.
    """
    
    response = model.generate_content(prompt)
    clean_json = response.text.strip().replace('```json', '').replace('```', '')
    return json.loads(clean_json)


# --- STREAMLIT UI ---
st.set_page_config(page_title="Expense Agent", page_icon="📝")
st.title("Agentic Expense Manager")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_duplicate" not in st.session_state:
    st.session_state.pending_duplicate = None


for msg in st.session_state.messages:
    with st.chat_message(msg['role']):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ex: add 200 for kids tuition"):
    st.session_state.messages.append({"role":"user", "content":prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        # Check if user is responding to a pending duplicate
        if st.session_state.pending_duplicate:
            with st.spinner("Analyzing your response.."):
                clarification_analysis = analyze_duplicate_clarification(prompt, st.session_state.pending_duplicate)
            
            if clarification_analysis.get('is_clarification', False):
                # User is saying this is NOT a duplicate - add with LLM-extracted context
                extracted_data = st.session_state.pending_duplicate.copy()
                
                # Append context from LLM analysis to remarks
                remarks_addition = clarification_analysis.get('remarks_addition', '').strip()
                if remarks_addition:
                    extracted_data['remarks'] = (extracted_data['remarks'] + " | " + remarks_addition).strip()
                
                success, message = update_excel(extracted_data)
                st.session_state.pending_duplicate = None  # Clear pending
                response = f"**Success!** {message}"
            else:
                # User chose to skip or is uncertain
                st.session_state.pending_duplicate = None
                response = "**Noted.** Skipping this entry."
        else:
            # Step 1 Use Gemini to "Understand"
            with st.spinner("Agent is thinking.."):
                extracted_data = extract_expense_details(prompt)
                # Use extracted month if provided, otherwise use current month as default
                if not extracted_data.get('month') or extracted_data['month'].strip() == "":
                    extracted_data['month'] = datetime.now().strftime("%B")
            
            # Step 2: Update excel
            success, message = update_excel(extracted_data)

            # Step 3: Respond to user
            if success:
                response = f"**Success!** {message}"
                st.session_state.pending_duplicate = None
            else:
                # Store duplicate entry for potential clarification
                st.session_state.pending_duplicate = extracted_data
                response = f"""**Notice:** {message}

    If this is NOT a duplicate and you want to add it anyway, please explain why:
    - "This is an advance payment for next month"
    - "This is a booking/deposit amount"
    - "This is a missed payment from last month"
    - Any other explanation

    Otherwise, I'll skip it."""
    except ValidationError as e:
        response = f"""
            **Sorry, I didn't understand or the input is not valid!** 😕

            Please provide expenses in a clearer format:

            **Examples:**
            - `add 200 for maths tuition`
            - `500 /- paid for electricity bill`
            - `1500 Rs. school fees, remarks: Due payment`
            - `100 for groceries, remarks: weekly shopping`

            **What I need:**
            - Amount (number)
            - Who received it (person/service name)
            - Optional: Any remarks or notes
        """
        st.session_state.pending_duplicate = None
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        response = f"**Error:** {str(e)}\n\n```\n{error_detail}\n```"
        st.error(response)
        st.session_state.pending_duplicate = None

    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role":"assistant", "content":response})


# --- ANALYSIS & REPORTING SECTION (SIDEBAR) ---
st.sidebar.markdown("---")
st.sidebar.title("📊 Analytics & Reports")

# Load data for analysis
expense_df = load_expense_data()

if expense_df.empty:
    st.sidebar.warning("No expense data yet. Start adding expenses!")
else:
    # Tabs for different reports
    analysis_tab = st.sidebar.radio(
        "Select Report Type:",
        ["Quick Stats", "Monthly Report", "Month Comparison"]
    )
    
    # --- QUICK STATS TAB ---
    if analysis_tab == "Quick Stats":
        st.sidebar.markdown("#### Quick Summary")
        stats = get_quick_stats(expense_df)
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.metric("Total Expenses", f"₹{stats['total_all_months']}")
        with col2:
            st.metric("Transactions", stats['total_transactions'])
        
        if stats['monthly_stats']:
            st.sidebar.markdown("**Monthly Breakdown:**")
            for month, data in stats['monthly_stats'].items():
                st.sidebar.write(f"**{month}**: ₹{data['total']} ({data['count']} transactions)")
            
            # Highest and lowest month
            col1, col2 = st.sidebar.columns(2)
            with col1:
                st.sidebar.write(f"🔝 **Highest**: {stats['highest_month']}")
                st.sidebar.write(f"₹{stats['highest_amount']}")
            with col2:
                st.sidebar.write(f"🔻 **Lowest**: {stats['lowest_month']}")
                st.sidebar.write(f"₹{stats['lowest_amount']}")
    
    # --- MONTHLY REPORT TAB ---
    elif analysis_tab == "Monthly Report":
        months = get_months_in_data(expense_df)
        
        if months:
            selected_month = st.sidebar.selectbox("Select Month:", months)
            
            if st.sidebar.button("📋 Generate Monthly Report"):
                with st.spinner("Generating report..."):
                    # Summary
                    summary = get_monthly_summary(expense_df, selected_month)
                    
                    st.sidebar.markdown("#### Monthly Summary")
                    st.sidebar.metric("Total Expense", f"₹{summary['total']}")
                    st.sidebar.metric("Transactions", summary['count'])
                    
                    # Pie chart
                    st.sidebar.markdown("**Expense Breakdown:**")
                    pie_chart = create_monthly_pie_chart(expense_df, selected_month)
                    if pie_chart:
                        st.sidebar.image(pie_chart, use_column_width=True)
                    
                    # LLM-generated report
                    st.sidebar.markdown("**AI-Generated Insights:**")
                    report = generate_monthly_report(expense_df, selected_month, genai.GenerativeModel('gemini-2.5-flash-lite'))
                    st.sidebar.markdown(report)
        else:
            st.sidebar.info("No months with data")
    
    # --- MONTH COMPARISON TAB ---
    elif analysis_tab == "Month Comparison":
        months = get_months_in_data(expense_df)
        
        if len(months) >= 2:
            col1, col2 = st.sidebar.columns(2)
            with col1:
                month1 = st.sidebar.selectbox("Month 1:", months, key="m1")
            with col2:
                month2 = st.sidebar.selectbox("Month 2:", months, index=1 if len(months) > 1 else 0, key="m2")
            
            if st.sidebar.button("📈 Generate Comparison"):
                if month1 != month2:
                    with st.spinner("Generating comparison..."):
                        # Comparison data
                        comparison = compare_months(expense_df, month1, month2)
                        
                        # Summary metrics
                        st.sidebar.markdown("#### Comparison Summary")
                        col1, col2 = st.sidebar.columns(2)
                        with col1:
                            st.sidebar.metric(month1, f"₹{comparison['total1']}")
                        with col2:
                            st.sidebar.metric(month2, f"₹{comparison['total2']}")
                        
                        # Trend
                        trend_emoji = "📈" if comparison['trend'] == "increased" else "📉" if comparison['trend'] == "decreased" else "➡️"
                        st.sidebar.write(
                            f"{trend_emoji} **Trend**: {comparison['trend'].upper()} "
                            f"({comparison['percent_change']:+.1f}% | ₹{comparison['difference']:+.2f})"
                        )
                        
                        # Comparison chart
                        st.sidebar.markdown("**Visual Comparison:**")
                        comparison_chart = create_comparison_chart(expense_df, month1, month2)
                        if comparison_chart:
                            st.sidebar.image(comparison_chart, use_column_width=True)
                        
                        # LLM-generated report
                        st.sidebar.markdown("**AI-Generated Insights:**")
                        report = generate_comparison_report(
                            expense_df, month1, month2,
                            genai.GenerativeModel('gemini-2.5-flash-lite')
                        )
                        st.sidebar.markdown(report)
                else:
                    st.sidebar.error("Select two different months!")
        else:
            st.sidebar.info(f"Need at least 2 months with data. You have {len(months)} month(s).")



 