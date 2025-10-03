import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from datetime import date

# ---------- CONFIG ----------
# Path to your Firebase service account JSON
FIREBASE_CRED_PATH = "path_to_your_service_account.json"
DATABASE_URL = "https://your-project-id-default-rtdb.firebaseio.com/"

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CRED_PATH)
    firebase_admin.initialize_app(cred, {
        'databaseURL': DATABASE_URL
    })

# ---------- UTILITY ----------
def get_user_data(user):
    ref = db.reference(f"users/{user}")
    return ref.get() or {}

def save_user_data(user, data):
    ref = db.reference(f"users/{user}")
    ref.set(data)

def get_days_in_month(year, month):
    from datetime import timedelta
    if month == 12:
        next_month = date(year+1, 1, 1)
    else:
        next_month = date(year, month+1, 1)
    return (next_month - timedelta(days=1)).day

# ---------- STREAMLIT APP ----------
st.title("💰 Cloud Expense Tracker")

user = st.text_input("Enter your name")
if not user:
    st.stop()

# Load user data from Firebase
data = get_user_data(user)
today = date.today()
year, month, day = today.year, today.month, today.day
month_key = f"{year}-{month:02d}"
day_key = f"{year}-{month:02d}-{day:02d}"

if month_key not in data:
    budget = st.number_input(f"Enter your monthly budget for {month_key}:", min_value=0)
    if st.button("Set Budget"):
        days_in_month = get_days_in_month(year, month)
        daily_budget = budget // days_in_month
        data[month_key] = {
            "budget": budget,
            "days": {},
            "carryover": 0,
            "daily_budget": daily_budget
        }
        save_user_data(user, data)
        st.success(f"Monthly budget of ₹{budget} saved!")

if month_key in data:
    monthly_data = data[month_key]
    # Yesterday's balance
    prev_balance = monthly_data["carryover"]
    todays_budget = prev_balance
    st.subheader("📅 Daily Tracker")
    st.write(f"Today's available budget: ₹{todays_budget}")

    spent = st.number_input("Enter today's spending:", min_value=0)
    if st.button("Record Expense"):
        new_balance = todays_budget - spent
        monthly_data["days"][day_key] = {
            "spent": spent,
            "budget": new_balance,
            "daily_budget": todays_budget
        }
        monthly_data["carryover"] = new_balance
        save_user_data(user, data)
        st.success(f"Expense of ₹{spent} recorded! Remaining balance: ₹{new_balance}")

    if st.button("Show Monthly Summary"):
        days = monthly_data["days"]
        if not days:
            st.info("No daily expense recorded yet.")
        else:
            total_spent = sum(day["spent"] for day in days.values())
            remaining_balance = monthly_data["carryover"]
            avg_daily = sum(day["daily_budget"] for day in days.values())/len(days)
            max_spent = max(day["spent"] for day in days.values())
            min_spent = min(day["spent"] for day in days.values())
            st.subheader("📊 Monthly Summary")
            st.write(f"Total Spent: ₹{total_spent}")
            st.write(f"Remaining Balance: ₹{remaining_balance}")
            st.write(f"Avg Daily Budget: ₹{avg_daily:.2f}")
            st.write(f"Max Daily Spending: ₹{max_spent}")
            st.write(f"Min Daily Spending: ₹{min_spent}")
