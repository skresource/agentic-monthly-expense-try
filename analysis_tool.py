"""
ANALYSIS & REPORTING TOOL
========================
This module handles all analytics and reporting functionality for expense tracking.
Includes monthly summaries, comparisons, visualizations, and LLM-powered insights.
"""

import pandas as pd
import json
import numpy as np
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
import matplotlib.pyplot as plt
import io


# --- HELPER FUNCTIONS ---

def convert_to_native_types(obj):
    """
    Convert pandas/numpy data types to native Python types for JSON serialization.
    
    Args:
        obj: Object to convert
        
    Returns:
        Converted object with native Python types
    """
    if isinstance(obj, dict):
        return {k: convert_to_native_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_native_types(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (pd.Timestamp, datetime)):
        return str(obj)
    else:
        return obj


# --- DATA LOADING FUNCTIONS ---

def load_expense_data(file_path: str = "./assets/monthley-expneses.xlsx") -> pd.DataFrame:
    """
    Load expense data from Excel file.
    
    Args:
        file_path (str): Path to the Excel file
        
    Returns:
        pd.DataFrame: Loaded expense data with cleaned columns
    """
    if not Path(file_path).exists():
        return pd.DataFrame()
    
    df = pd.read_excel(file_path)
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    return df


def get_months_in_data(df: pd.DataFrame) -> list:
    """
    Get list of unique months in the expense data.
    
    Args:
        df (pd.DataFrame): Expense dataframe
        
    Returns:
        list: Sorted list of unique months
    """
    if df.empty:
        return []
    return sorted(df['Month'].unique().tolist())


# --- MONTHLY SUMMARY FUNCTIONS ---

def get_monthly_summary(df: pd.DataFrame, month: str) -> dict:
    """
    Get expense summary for a specific month.
    
    Args:
        df (pd.DataFrame): Expense dataframe
        month (str): Month name (e.g., "February")
        
    Returns:
        dict: Summary with total, count, by subject breakdown
    """
    if df.empty:
        return {
            'month': month,
            'total': 0,
            'count': 0,
            'by_subject': {},
            'exists': False
        }
    
    month_data = df[df['Month'] == month]
    
    if month_data.empty:
        return {
            'month': month,
            'total': 0,
            'count': 0,
            'by_subject': {},
            'exists': False
        }
    
    # Calculate totals
    total = month_data['Amount'].sum()
    count = len(month_data)
    
    # Group by subject
    by_subject = month_data.groupby('Sent To')['Amount'].agg(['sum', 'count']).to_dict('index')
    by_subject = {k: {'amount': v['sum'], 'count': v['count']} for k, v in by_subject.items()}
    
    return {
        'month': month,
        'total': round(total, 2),
        'count': count,
        'by_subject': by_subject,
        'exists': True,
        'entries': month_data.to_dict('records')
    }


def compare_months(df: pd.DataFrame, month1: str, month2: str) -> dict:
    """
    Compare expenses between two months.
    
    Args:
        df (pd.DataFrame): Expense dataframe
        month1 (str): First month name (e.g., "January")
        month2 (str): Second month name (e.g., "February")
        
    Returns:
        dict: Comparison data with totals, differences, and insights
    """
    summary1 = get_monthly_summary(df, month1)
    summary2 = get_monthly_summary(df, month2)
    
    total1 = summary1['total']
    total2 = summary2['total']
    difference = total2 - total1
    percent_change = ((total2 - total1) / total1 * 100) if total1 != 0 else 0
    
    return {
        'month1': month1,
        'month2': month2,
        'total1': total1,
        'total2': total2,
        'difference': round(difference, 2),
        'percent_change': round(percent_change, 2),
        'summary1': summary1,
        'summary2': summary2,
        'trend': 'increased' if difference > 0 else 'decreased' if difference < 0 else 'same'
    }


# --- VISUALIZATION FUNCTIONS ---

def create_monthly_pie_chart(df: pd.DataFrame, month: str) -> bytes:
    """
    Create a pie chart for monthly expenses by subject.
    
    Args:
        df (pd.DataFrame): Expense dataframe
        month (str): Month name
        
    Returns:
        bytes: Pie chart image as bytes (PNG)
    """
    summary = get_monthly_summary(df, month)
    
    if not summary['exists'] or not summary['by_subject']:
        return None
    
    # Prepare data
    subjects = list(summary['by_subject'].keys())
    amounts = [summary['by_subject'][s]['amount'] for s in subjects]
    
    # Create pie chart
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = plt.cm.Set3(range(len(subjects)))
    
    wedges, texts, autotexts = ax.pie(
        amounts,
        labels=subjects,
        autopct='%1.1f%%',
        colors=colors,
        startangle=90
    )
    
    # Enhance text
    for autotext in autotexts:
        autotext.set_color('black')
        autotext.set_fontsize(10)
        autotext.set_weight('bold')
    
    ax.set_title(f'Expenses for {month}\nTotal: ₹{summary["total"]}', fontsize=14, fontweight='bold')
    
    # Save to bytes
    img_buffer = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img_buffer, format='png', dpi=100)
    img_buffer.seek(0)
    plt.close()
    
    return img_buffer.getvalue()


def create_comparison_chart(df: pd.DataFrame, month1: str, month2: str) -> bytes:
    """
    Create a side-by-side bar chart comparing two months.
    
    Args:
        df (pd.DataFrame): Expense dataframe
        month1 (str): First month
        month2 (str): Second month
        
    Returns:
        bytes: Chart image as bytes (PNG)
    """
    comparison = compare_months(df, month1, month2)
    summary1 = comparison['summary1']
    summary2 = comparison['summary2']
    
    # Get all unique subjects
    all_subjects = set(summary1['by_subject'].keys()) | set(summary2['by_subject'].keys())
    all_subjects = sorted(list(all_subjects))
    
    # Prepare data
    amounts1 = [summary1['by_subject'].get(s, {}).get('amount', 0) for s in all_subjects]
    amounts2 = [summary2['by_subject'].get(s, {}).get('amount', 0) for s in all_subjects]
    
    # Create bar chart
    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(all_subjects))
    width = 0.35
    
    bars1 = ax.bar([i - width/2 for i in x], amounts1, width, label=month1, color='steelblue')
    bars2 = ax.bar([i + width/2 for i in x], amounts2, width, label=month2, color='coral')
    
    ax.set_xlabel('Subject', fontsize=12, fontweight='bold')
    ax.set_ylabel('Amount (₹)', fontsize=12, fontweight='bold')
    ax.set_title(f'Expense Comparison: {month1} vs {month2}', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(all_subjects, rotation=45, ha='right')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    # Save to bytes
    img_buffer = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img_buffer, format='png', dpi=100)
    img_buffer.seek(0)
    plt.close()
    
    return img_buffer.getvalue()


# --- LLM-POWERED INSIGHTS FUNCTIONS ---

def generate_monthly_report(df: pd.DataFrame, month: str, gemini_model=None) -> str:
    """
    Generate a natural language report for a month using LLM.
    
    Args:
        df (pd.DataFrame): Expense dataframe
        month (str): Month name
        gemini_model: Configured Gemini model
        
    Returns:
        str: LLM-generated natural language report
    """
    summary = get_monthly_summary(df, month)
    
    if not summary['exists']:
        return f"No expense data found for {month}."
    
    # Convert pandas types to native Python types for JSON serialization
    summary_converted = convert_to_native_types(summary)
    summary_json = json.dumps(summary_converted, indent=2)
    
    prompt = f"""
    Based on this expense summary for {month}, generate a CONCISE and BULLETED report:
    
    {summary_json}
    
    IMPORTANT: Keep response under 300 words. Use bullet points for clarity.
    
    Format your response with:
    • Total expenses and transaction count
    • Top 3 spending categories (with amounts)
    • Average per transaction
    • Key observations (2-3 bullet points)
    • One brief recommendation
    
    Be direct, concise, and use bullet points. No long paragraphs I am using INR or Indian Rupee as currency not USD.
    """
    
    response = gemini_model.generate_content(prompt)
    return response.text


def generate_comparison_report(df: pd.DataFrame, month1: str, month2: str, gemini_model=None) -> str:
    """
    Generate a natural language comparison report between two months using LLM.
    
    Args:
        df (pd.DataFrame): Expense dataframe
        month1 (str): First month
        month2 (str): Second month
        gemini_model: Configured Gemini model
        
    Returns:
        str: LLM-generated natural language comparison report
    """
    comparison = compare_months(df, month1, month2)
    # Convert pandas types to native Python types for JSON serialization
    comparison_converted = convert_to_native_types(comparison)
    comparison_json = json.dumps(comparison_converted, indent=2)
    
    prompt = f"""
    Generate a CONCISE, BULLETED comparison report between {month1} and {month2}:
    
    {comparison_json}
    
    IMPORTANT: Keep response under 300 words. Use bullet points for clarity.
    
    Format your response with:
    • Overall spending trend with percentage change and absolute difference
    • Categories with biggest increase/decrease (top 2-3)
    • Key insights (2-3 bullet points)
    • One brief recommendation
    
    Be direct, concise, and use bullet points. No long paragraphs. I am using INR or Indian Rupee as currency not USD
    """
    
    response = gemini_model.generate_content(prompt)
    return response.text


def get_quick_stats(df: pd.DataFrame) -> dict:
    """
    Get quick statistics for all months.
    
    Args:
        df (pd.DataFrame): Expense dataframe
        
    Returns:
        dict: Statistics for all months
    """
    if df.empty:
        return {
            'total_all_months': 0,
            'total_transactions': 0,
            'monthly_stats': {},
            'highest_month': None,
            'lowest_month': None
        }
    
    months = get_months_in_data(df)
    monthly_stats = {}
    
    for month in months:
        summary = get_monthly_summary(df, month)
        monthly_stats[month] = {
            'total': summary['total'],
            'count': summary['count'],
            'average': round(summary['total'] / summary['count'], 2) if summary['count'] > 0 else 0
        }
    
    # Find highest and lowest
    if monthly_stats:
        highest_month = max(monthly_stats.items(), key=lambda x: x[1]['total'])
        lowest_month = min(monthly_stats.items(), key=lambda x: x[1]['total'])
    else:
        highest_month = None
        lowest_month = None
    
    total_all = sum(s['total'] for s in monthly_stats.values())
    total_transactions = sum(s['count'] for s in monthly_stats.values())
    
    return {
        'total_all_months': round(total_all, 2),
        'total_transactions': total_transactions,
        'monthly_stats': monthly_stats,
        'highest_month': highest_month[0] if highest_month else None,
        'highest_amount': round(highest_month[1]['total'], 2) if highest_month else 0,
        'lowest_month': lowest_month[0] if lowest_month else None,
        'lowest_amount': round(lowest_month[1]['total'], 2) if lowest_month else 0,
        'average_per_month': round(total_all / len(months), 2) if months else 0
    }
