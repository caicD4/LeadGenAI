from core.orchestrator import run_lead_generation
from database.database import init_db, get_leads


def main():
    init_db()

    while True:
        print("\n=== LeadGenAI ===")
        print("1. Find and research leads")
        print("2. View saved leads")
        print("3. Exit")

        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            criteria = input(
                "\nWhat kind of leads do you want to find?\n> "
            ).strip()

            if not criteria:
                print("\nPlease enter some criteria.")
                continue

            try:
                leads = run_lead_generation(
                    criteria,
                    max_results=5,
                )

                print(
                    f"\nCompleted. "
                    f"{len(leads)} lead(s) processed."
                )

            except Exception as exc:
                print(f"\nLead generation failed: {exc}")

        elif choice == "2":
            leads = get_leads()

            if not leads:
                print("\nNo leads saved yet.")
                continue

            print("\n=== Saved Leads ===")

            for lead in leads:
                print(f"\nID: {lead[0]}")
                print(f"Company: {lead[1]}")
                print(f"Industry: {lead[2]}")
                print(f"Info: {lead[3]}")
                print(f"Research: {lead[4]}")
                print("-" * 50)

        elif choice == "3":
            print("\nGoodbye!")
            break

        else:
            print("\nInvalid choice. Please choose 1, 2, or 3.")


if __name__ == "__main__":
    main()