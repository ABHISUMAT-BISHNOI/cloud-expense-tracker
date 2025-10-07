import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from datetime import date, timedelta
import pandas as pd

# ---------- CONFIG (No Changes Here) ----------
try:
    firebase_dict = dict(st.secrets["firebase"])
except FileNotFoundError:
    st.error("Firebase secrets file not found. Please add it to your Streamlit secrets.")
    st.stop()
except Exception as e:
    st.error(f"Error loading Firebase secrets: {e}")
    st.stop()

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(firebase_dict)
        firebase_admin.initialize_app(cred, {
            'databaseURL': "https://expense-tracker-5f660-default-rtdb.asia-southeast1.firebasedatabase.app/"
        })
    except Exception as e:
        st.error(f"Firebase initialization failed. Please check your secrets configuration. Error: {e}")
        st.stop()

# ---------- UTILITY (No Changes Here) ----------
def get_user_data(user):
    ref = db.reference(f"users/{user}")
    return ref.get() or {}

def save_user_data(user, data):
    ref = db.reference(f"users/{user}")
    ref.set(data)

def get_days_in_month(year, month):
    if month == 12:
        next_month_first_day = date(year + 1, 1, 1)
    else:
        next_month_first_day = date(year, month + 1, 1)
    return (next_month_first_day - timedelta(days=1)).day

# ---------- STREAMLIT APP ----------
st.set_page_config(layout="centered", page_title="💰 Cloud Expense Tracker")
st.title("💰 Cloud Expense Tracker")

if 'user' not in st.session_state:
    st.session_state.user = ""

user_input = st.text_input("Enter your name to load your tracker", st.session_state.user)

if user_input:
    st.session_state.user = user_input
else:
    st.info("Please enter a name to begin tracking.")
    st.stop()

user = st.session_state.user
try:
    data = get_user_data(user)
except Exception as e:
    st.error(f"Could not connect to the database. Please check the connection. Error: {e}")
    st.stop()

today = date.today()
year, month, day = today.year, today.month, today.day
month_key = f"{year}-{month:02d}"
day_key = f"{year}-{month:02d}-{day:02d}"

# --- LOGIC FOR SETTING A NEW MONTH'S BUDGET ---
if month_key not in data:
    st.header(f"Setup for {today.strftime('%B %Y')}")

    # --- Standard carryover logic ---
    carryover_from_prev_month = 0
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    prev_month_key = f"{prev_year}-{prev_month:02d}"
    if prev_month_key in data:
        carryover_from_prev_month = data[prev_month_key].get('rolling_balance', 0)

    if carryover_from_prev_month >= 0:
        st.success(f"🎉 Bonus! You have a surplus of ₹{carryover_from_prev_month:.2f} from last month.")
    else:
        st.warning(f"⚠️ You have a deficit of ₹{carryover_from_prev_month:.2f} from last month. This will be deducted from your new budget.")

    new_budget = st.number_input(f"Enter your base budget for {today.strftime('%B %Y')}:", min_value=0.0, format="%.2f")

    # --- NEW: Handle Mid-Month Start ---
    past_spending = 0
    if today.day > 1:
        st.info(f"Since you're starting on the {day}{'st' if day == 1 else 'nd' if day == 2 else 'rd' if day == 3 else 'th'}, please enter your total spending for this month so far.")
        yesterday_str = (today - timedelta(days=1)).strftime('%B %d')
        past_spending = st.number_input(f"Total spent from {today.strftime('%B')} 1st to {yesterday_str}:", min_value=0.0, format="%.2f", key="past_spending")

    if st.button("Set Monthly Budget"):
        if new_budget > 0:
            total_budget = new_budget + carryover_from_prev_month
            days_in_this_month = get_days_in_month(year, month)
            standard_daily_budget = total_budget / days_in_this_month
            
            initial_days_data = {}
            initial_rolling_balance = 0

            # If starting mid-month, create a summary entry for the previous day
            if today.day > 1:
                yesterday = today - timedelta(days=1)
                yesterday_key = yesterday.strftime('%Y-%m-%d')
                
                budget_up_to_yesterday = standard_daily_budget * yesterday.day
                balance_after_past_spending = budget_up_to_yesterday - past_spending

                initial_days_data[yesterday_key] = {
                    "spent": past_spending,
                    "available_budget_before_spend": budget_up_to_yesterday,
                    "rolling_balance_after_spend": balance_after_past_spending,
                    "is_summary": True # A flag to know this was a summary entry
                }
                initial_rolling_balance = balance_after_past_spending
            
            data[month_key] = {
                "base_budget": new_budget,
                "total_budget": total_budget,
                "standard_daily_budget": standard_daily_budget,
                "rolling_balance": initial_rolling_balance,
                "days": initial_days_data
            }
            save_user_data(user, data)
            st.success(f"Budget set for {today.strftime('%B %Y')}! Your tracker is ready.")
            st.rerun()
        else:
            st.error("Please enter a budget greater than 0.")

# --- LOGIC FOR DAILY TRACKING AND VIEWING SUMMARY (No changes needed here) ---
if month_key in data:
    monthly_data = data[month_key]
    standard_daily_budget = monthly_data['standard_daily_budget']

    recorded_days = monthly_data.get('days', {})
    if not recorded_days:
        last_recorded_date = date(year, month, 1) - timedelta(days=1)
        last_known_balance = 0
    else:
        last_recorded_day_key = max(recorded_days.keys())
        last_recorded_date = date.fromisoformat(last_recorded_day_key)
        last_known_balance = recorded_days[last_recorded_day_key]['rolling_balance_after_spend']

    days_missed = (today - last_recorded_date).days
    todays_available_budget = last_known_balance + (days_missed * standard_daily_budget)

    st.header("📅 Daily Tracker")
    if todays_available_budget >= 0:
        st.info(f"Today's available budget: ₹{todays_available_budget:.2f}")
    else:
        st.error(f"Today's available budget: ₹{todays_available_budget:.2f}")

    spent = st.number_input("Enter today's spending:", min_value=0.0, key=f"spent_{day_key}", format="%.2f")

    if st.button("Record Expense"):
        if 'days' not in monthly_data:
            monthly_data['days'] = {}

        new_rolling_balance = todays_available_budget - spent
        monthly_data['days'][day_key] = {
            "spent": spent,
            "available_budget_before_spend": todays_available_budget,
            "rolling_balance_after_spend": new_rolling_balance
        }
        monthly_data['rolling_balance'] = new_rolling_balance
        save_user_data(user, data)
        st.success(f"Expense of ₹{spent:.2f} recorded! Your new rolling balance is ₹{new_rolling_balance:.2f}")
        st.balloons()
        st.rerun()

    st.header("📊 Monthly Analysis")
    days = monthly_data.get("days", {})
    if not days:
        st.info("No expenses recorded yet for this month.")
    else:
        total_spent = sum(day_data["spent"] for day_data in days.values())
        base_budget = monthly_data['base_budget']
        total_budget = monthly_data['total_budget']
        current_balance = monthly_data['rolling_balance']

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Budget", f"₹{total_budget:.2f}", f"Base: ₹{base_budget:.2f}")
        col2.metric("Total Spent", f"₹{total_spent:.2f}")
        col3.metric("Remaining Balance", f"₹{current_balance:.2f}")

        st.write("---")
        st.subheader("Spending History")
        expense_list = [{'Date': k, 'Spent': v['spent'], 'Available': f"₹{v['available_budget_before_spend']:.2f}", 'Balance After': f"₹{v['rolling_balance_after_spend']:.2f}"} for k, v in sorted(days.items())]
        df = pd.DataFrame(expense_list)
        st.dataframe(df, use_container_width=True)

