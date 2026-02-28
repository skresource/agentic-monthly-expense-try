import pandas as pd
from datetime import datetime
import os
from pydantic import BaseModel, Field, validator

# --- DATA MODEL ---
class ExpenseData(BaseModel):
    amount: float = Field(..., gt=0, description="Expense amount")
    subject: str = Field(..., min_length=1, description="Who is the money sent to")
    month: str = Field(..., description="Month of the expense")
    remarks: str = Field(default="", description="Additional notes")
    
    @validator('amount')
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than 0')
        return round(v, 2)
    
    @validator('subject', 'remarks')
    def strip_whitespace(cls, v):
        return v.strip() if isinstance(v, str) else v

def update_excel(data: ExpenseData | dict):
    # Validate input data
    if isinstance(data, dict):
        data = ExpenseData(**data)
    
    file_name= "./assets/monthley-expneses.xlsx"
    date_str = datetime.now().strftime("%d-%b-%y")

    new_row = {
        "Date": date_str,
        "Amount": data.amount,
        "Sent To": data.subject,
        "Month": data.month,
        "Remarks": data.remarks
    }

    if os.path.exists(file_name):
        df = pd.read_excel(file_name)
        # Strip whitespace from column names and standardize them
        df.columns = df.columns.str.strip()
        
        # Ensure all required columns exist
        required_cols = ["Date", "Amount", "Sent To", "Month", "Remarks"]
        if not all(col in df.columns for col in required_cols):
            print(f"Warning: Excel file has these columns: {list(df.columns)}")
            print(f"Expected columns: {required_cols}")
            # Reset to expected columns if mismatch
            df = pd.DataFrame(columns=required_cols)
        
        if not df.empty:
            is_duplicate = not df[
                (df['Date'] == date_str) &
                (df['Amount'] == data.amount) &
                (df['Sent To'] == data.subject)
            ].empty
            if is_duplicate:
                return False, "Duplicate entry found today"
    else:
        df = pd.DataFrame(columns=["Date", "Amount", "Sent To", "Month", "Remarks"])
    
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_excel(file_name, index=False)
    return True, f"Added: {data.amount} for {data.subject}"

    
         
