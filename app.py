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

# --- LOGIC FOR SETTING A NEW MONTH'S BUDGET (No Major Changes) ---
if month_key not in data:
    st.header(f"Setup for {today.strftime('%B %Y')}")
    # ... (code for setting up a new month is unchanged) ...
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
            if today.day > 1:
                yesterday = today - timedelta(days=1)
                yesterday_key = yesterday.strftime('%Y-%m-%d')
                budget_up_to_yesterday = standard_daily_budget * yesterday.day
                balance_after_past_spending = budget_up_to_yesterday - past_spending
                initial_days_data[yesterday_key] = {
                    "spent": past_spending,
                    "available_budget_before_spend": budget_up_to_yesterday,
                    "rolling_balance_after_spend": balance_after_past_spending,
                    "is_summary": True
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


# --- MAIN APP LOGIC FOR AN EXISTING MONTH ---
if month_key in data:
    monthly_data = data[month_key]
    standard_daily_budget = monthly_data['standard_daily_budget']

    # --- Determine the last recorded day and calculate missed days ---
    recorded_days = monthly_data.get('days', {})
    if not recorded_days:
        last_recorded_date = date(year, month, 1) - timedelta(days=1)
    else:
        last_recorded_day_key = max(recorded_days.keys())
        last_recorded_date = date.fromisoformat(last_recorded_day_key)
    
    days_missed = (today - last_recorded_date).days

    # --- NEW FEATURE: CATCH-UP FOR MISSED DAYS ---
    if days_missed > 1:
        st.header("🏃‍♂️ Catch up on your spending")
        missed_start_date = last_recorded_date + timedelta(days=1)
        missed_end_date = today - timedelta(days=1)
        
        st.warning(f"You haven't recorded expenses from **{missed_start_date.strftime('%B %d')}** to **{missed_end_date.strftime('%B %d')}**. Please enter the total amount spent in this period.")
        
        missed_spending = st.number_input("Total spent during missed days:", min_value=0.0, format="%.2f", key="missed_spending")

        if st.button("Record Missed Expenses"):
            # Calculate the starting balance for the missed period
            last_known_balance = recorded_days.get(last_recorded_day_key, {}).get('rolling_balance_after_spend', 0)
            
            # Add the budget for all missed days (excluding today)
            budget_for_missed_period = standard_daily_budget * (days_missed - 1)
            available_for_missed_period = last_known_balance + budget_for_missed_period
            
            # Calculate the new balance after accounting for the spending
            new_balance = available_for_missed_period - missed_spending

            # Create a single summary entry for the entire missed period
            summary_key = missed_end_date.strftime('%Y-%m-%d')
            monthly_data['days'][summary_key] = {
                "spent": missed_spending,
                "available_budget_before_spend": available_for_missed_period,
                "rolling_balance_after_spend": new_balance,
                "is_summary": True,
                "summary_period": f"{missed_start_date.strftime('%d %b')} - {missed_end_date.strftime('%d %b')}"
            }
            save_user_data(user, data)
            st.success("Missed expenses recorded! Your tracker is now up to date.")
            st.rerun()
    
    # --- REGULAR DAILY TRACKER (only shows if user is up to date) ---
    else:
        last_known_balance = recorded_days.get(last_recorded_day_key, {}).get('rolling_balance_after_spend', 0) if recorded_days else 0
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
            # The main rolling_balance is now only updated on actual expense recording
            monthly_data['rolling_balance'] = new_rolling_balance
            save_user_data(user, data)
            st.success(f"Expense of ₹{spent:.2f} recorded!")
            st.balloons()
            st.rerun()

    # --- REVISED MONTHLY ANALYSIS (always visible) ---
    st.header("📊 Monthly Analysis")
    days = monthly_data.get("days", {})
    if not days:
        st.info("No expenses recorded yet for this month.")
    else:
        # Calculate today's budget again for display purposes
        last_known_balance = recorded_days.get(max(recorded_days.keys()), {}).get('rolling_balance_after_spend', 0) if recorded_days else 0
        todays_available_budget_display = last_known_balance + (days_missed * standard_daily_budget)

        total_spent = sum(day_data["spent"] for day_data in days.values())
        total_budget = monthly_data['total_budget']
        month_remaining = total_budget - total_spent
        
        # --- NEW 4-COLUMN LAYOUT FOR CLARITY ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Budget", f"₹{total_budget:.2f}")
        col2.metric("Total Spent", f"₹{total_spent:.2f}")
        col3.metric("Month Remaining", f"₹{month_remaining:.2f}", help="This is your Total Budget minus Total Spent.")
        col4.metric("Available Today", f"₹{todays_available_budget_display:.2f}", help="This is your rolling balance available to spend right now.")
        
        st.write("---")
        st.subheader("Spending History")
        expense_list = []
        for k, v in sorted(days.items()):
            # If it's a summary entry for missed days, display the period
            date_label = v.get("summary_period", k)
            expense_list.append({'Date': date_label, 'Spent': v['spent'], 'Available': f"₹{v['available_budget_before_spend']:.2f}", 'Balance After': f"₹{v['rolling_balance_after_spend']:.2f}"})
        
        df = pd.DataFrame(expense_list)
        st.dataframe(df, use_container_width=True)




