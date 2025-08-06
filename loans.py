import json
import textwrap
import uuid
from http.client import responses

import bcrypt
from dateutil.relativedelta import relativedelta
from supabase import create_client, Client
from flask import session
import os
import random
import string
import smtplib
from email.message import EmailMessage
import pandas as pd
from datetime import datetime, timedelta
import os


class Loans:
    """contains methods required for the home template"""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

        # email authentication
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.email_password = os.getenv('EMAIL_PASSWORD')

    def map_payments_by_month(self, organisation_id):
        """
        Returns a dictionary mapping loan_id to set of paid months (YYYY-MM)
        Only includes repayments for the given organisation.
        """
        from collections import defaultdict
        payments_by_month = defaultdict(set)

        try:
            response = (
                self.supabase
                .table('loan_repayments')
                .select('*')
                .eq('payment_status', 'complete')
                .eq('organisation_id', organisation_id)
                .execute()
            )
            repayments = response.data

            for r in repayments:
                try:
                    month_paid = datetime.fromisoformat(r['created_at']).strftime("%Y-%m")
                    payments_by_month[r['loan_id']].add(month_paid)
                except Exception as e:
                    print(f"Date parse error for repayment {r}: {e}")

            return payments_by_month

        except Exception as e:
            print(f"Error retrieving repayments: {e}")
            return defaultdict(set)

    def generate_payment_status(self, organisation_id):
        """
        Returns a dict mapping loan_id to {
          'monthly_payment': float,
          'borrower_id': str,
          'payment_status_by_month': { month: status }
        }
        Only includes loans belonging to the specified organisation.
        """
        try:
            loans_response = (
                self.supabase
                .table('loans')
                .select('*')
                .eq('organisation_id', organisation_id)
                .execute()
            )
            loans = loans_response.data

            payments_by_month = self.map_payments_by_month(organisation_id)
            today = datetime.today()
            result = {}

            for loan in loans:
                loan_id = loan['id']
                created_at = datetime.fromisoformat(loan['created_at'])
                start_date = created_at + relativedelta(months=1)  # repayments start 1 month after creation
                months = loan['term_months']

                loan_status = {}

                for i in range(months):
                    due_date = start_date + relativedelta(months=i)
                    month_key = due_date.strftime("%Y-%m")

                    if due_date > today:
                        status = "Upcoming"
                    elif month_key in payments_by_month.get(loan_id, set()):
                        status = "Paid"
                    else:
                        status = "Missed"

                    loan_status[month_key] = status

                result[loan_id] = {
                    "monthly_payment": loan.get("monthly_payment"),
                    "borrower_id": loan.get("borrower_id"),
                    "organisation_id": organisation_id,
                    "payment_status_by_month": loan_status
                }

            return result

        except Exception as e:
            print(f"Error generating payment status: {e}")
            return {}

    def get_monthly_payment_schedules_for_template(self, organisation_id):
        """
        Returns organized payment schedule data ready for template consumption.
        Groups upcoming payments by month with all necessary display information.

        Returns:
            dict: {
                'months_with_payments': [
                    {
                        'month': '2025-01',
                        'month_display': 'January 2025',
                        'total_amount': 1500.00,
                        'loan_count': 3,
                        'loans': [
                            {
                                'loan_id': 'xxx',
                                'monthly_payment': 500.00,
                                'borrower_id': 'yyy',
                                'status': 'Upcoming'
                            }
                        ]
                    }
                ],
                'has_upcoming_payments': True,
                'total_upcoming_months': 2
            }
        """
        try:
            # Get the raw payment status data
            payment_data = self.generate_payment_status(organisation_id)

            if not payment_data:
                return {
                    'months_with_payments': [],
                    'has_upcoming_payments': False,
                    'total_upcoming_months': 0
                }

            # Dictionary to collect upcoming payments by month
            months_with_payments = {}

            # Process each loan's payment schedule
            for loan_id, loan_info in payment_data.items():
                for month, status in loan_info['payment_status_by_month'].items():
                    if status == "Upcoming":
                        # Initialize month entry if not exists
                        if month not in months_with_payments:
                            months_with_payments[month] = {
                                'month': month,
                                'month_display': self._format_month_display(month),
                                'total_amount': 0.0,
                                'loan_count': 0,
                                'loans': []
                            }

                        # Add loan payment to this month
                        monthly_payment = loan_info.get('monthly_payment', 0.0)
                        months_with_payments[month]['total_amount'] += monthly_payment
                        months_with_payments[month]['loan_count'] += 1
                        months_with_payments[month]['loans'].append({
                            'loan_id': loan_id,
                            'monthly_payment': monthly_payment,
                            'borrower_id': loan_info.get('borrower_id'),
                            'status': status
                        })

            # Convert to sorted list by month
            sorted_months = sorted(months_with_payments.values(), key=lambda x: x['month'])

            return {
                'months_with_payments': sorted_months,
                'has_upcoming_payments': len(sorted_months) > 0,
                'total_upcoming_months': len(sorted_months)
            }

        except Exception as e:
            print(f"Error generating monthly payment schedules for template: {e}")
            return {
                'months_with_payments': [],
                'has_upcoming_payments': False,
                'total_upcoming_months': 0
            }

    def _format_month_display(self, month_key):
        """
        Convert month key (YYYY-MM) to display format (Month YYYY)

        Args:
            month_key (str): Month in format 'YYYY-MM'

        Returns:
            str: Formatted month like 'January 2025'
        """
        try:
            year, month_num = month_key.split('-')
            month_names = [
                '', 'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'
            ]
            return f"{month_names[int(month_num)]} {year}"
        except (ValueError, IndexError) as e:
            print(f"Error formatting month display for {month_key}: {e}")
            return month_key  # fallback to original format

    def get_monthly_loan_repayments(self, organisation_id):
        """Returns monthly loan repayments for all loans belonging to a specific organisation"""
        try:
            loans_response = self.supabase.table('loans').select("*").eq('organisation_id', organisation_id).execute()
            loans = loans_response.data

            if not loans:
                return {}

            # Map loans by id for lookup
            loan_map = {loan['id']: loan for loan in loans}

            loan_ids = list(loan_map.keys())

            repayments_response = self.supabase.table('loan_repayments') \
                .select("*") \
                .in_('loan_id', loan_ids) \
                .execute()

            repayments = repayments_response.data

            from collections import defaultdict
            from datetime import datetime

            monthly_summary = defaultdict(list)

            for repayment in repayments:
                created_date = datetime.fromisoformat(repayment['created_at'])
                month_key = created_date.strftime('%Y-%m')

                loan_id = repayment['loan_id']
                loan = loan_map.get(loan_id)

                if loan:
                    monthly_summary[month_key].append({
                        'loan_id': loan_id,
                        'borrower_id': repayment.get('borrower_id'),
                        'organisation_id': repayment.get('organisation_id'),
                        'payment_amount': repayment.get('payment_amount'),
                        'principal_component': repayment.get('principal_component'),
                        'interest_component': repayment.get('interest_component'),
                        'balance': repayment.get('balance'),
                        'payment_status': repayment.get('payment_status'),
                        'monthly_payment': loan.get('monthly_payment'),
                        'term_months': loan.get('term_months'),
                    })

            return dict(monthly_summary)

        except Exception as e:
            print(f"Error generating payment status: {e}")
            return {}

    def get_borrower_payment_details_for_month(self, organisation_id, month):
        """
        Returns a list of borrower details for all loans that have upcoming payments in a specific month.

        Args:
            organisation_id (str): Organisation ID to filter loans
            month (str): Month in format 'YYYY-MM' to get borrowers for

        Returns:
            list: List of dictionaries with:
                - loan_id
                - borrower_id
                - first_name
                - last_name
                - nrc_number
                - phone_number (if available)
                - monthly_payment
                - payment_status
            Empty list if no borrowers found.
        """
        try:
            # Step 1: Get payment status data for the organisation
            payment_data = self.generate_payment_status(organisation_id)

            if not payment_data:
                return []

            # Step 2: Find all loan IDs that have upcoming payments for the specified month
            loan_ids_for_month = []
            loan_payment_info = {}

            for loan_id, loan_info in payment_data.items():
                month_status = loan_info.get('payment_status_by_month', {}).get(month)
                if month_status == "Upcoming":
                    loan_ids_for_month.append(loan_id)
                    loan_payment_info[loan_id] = {
                        'monthly_payment': loan_info.get('monthly_payment'),
                        'borrower_id': loan_info.get('borrower_id'),
                        'status': month_status
                    }

            if not loan_ids_for_month:
                return []

            # Step 3: Get unique borrower IDs
            borrower_ids = list(set([
                loan_payment_info[loan_id]['borrower_id']
                for loan_id in loan_ids_for_month
                if loan_payment_info[loan_id]['borrower_id']
            ]))

            if not borrower_ids:
                return []

            # Step 4: Query borrowers table for all borrower IDs
            borrowers_response = (
                self.supabase
                .table('borrowers')
                .select('id, first_name, last_name, nrc_number, phone')
                .in_('id', borrower_ids)
                .execute()
            )
            borrowers_data = borrowers_response.data

            # Step 5: Create a lookup dictionary for borrower data
            borrowers_lookup = {borrower['id']: borrower for borrower in borrowers_data}

            # Step 6: Build the result list
            result = []
            for loan_id in loan_ids_for_month:
                loan_info = loan_payment_info[loan_id]
                borrower_id = loan_info['borrower_id']
                borrower_data = borrowers_lookup.get(borrower_id)

                if borrower_data:
                    result.append({
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "first_name": borrower_data.get('first_name'),
                        "last_name": borrower_data.get('last_name'),
                        "nrc_number": borrower_data.get('nrc_number'),
                        "phone_number": borrower_data.get('phone'),
                        "monthly_payment": loan_info.get('monthly_payment'),
                        "payment_status": loan_info.get('status')
                    })

            return result

        except Exception as e:
            print(f"Error fetching borrower payment details for month {month}: {e}")
            return []

    def get_borrower_payment_details(self, loans, loan_id):
        """
        Returns borrower details + monthly payment for a specific loan ID.
        (Kept for backward compatibility)

        Args:
            loans (dict): Dict of loan data keyed by loan_id.
            loan_id (str): Specific loan ID to extract details for.

        Returns:
            dict | None: Dictionary with borrower and payment details or None if not found.
        """
        try:
            # Step 1: Get the specific loan
            loan_info = loans.get(loan_id)
            if not loan_info:
                return None

            borrower_id = loan_info.get('borrower_id')
            if not borrower_id:
                return None

            # Step 2: Query borrowers table for this borrower_id
            borrower_response = (
                self.supabase
                .table('borrowers')
                .select('id, first_name, last_name, nrc_number, phone_number')
                .eq('id', borrower_id)
                .limit(1)
                .execute()
            )
            borrower_data = borrower_response.data[0] if borrower_response.data else None

            if not borrower_data:
                return None

            # Step 3: Return merged result
            return {
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "first_name": borrower_data.get('first_name'),
                "last_name": borrower_data.get('last_name'),
                "nrc_number": borrower_data.get('nrc_number'),
                "phone_number": borrower_data.get('phone'),
                "monthly_payment": loan_info.get('monthly_payment')
            }

        except Exception as e:
            print(f"Error fetching borrower payment details: {e}")
            return None


# Example usage and testing
test = Loans()
print(json.dumps(test.get_monthly_payment_schedules_for_template('ee8278fc-66e6-4a0f-a6bb-3525657f98b8')))
