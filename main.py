from agents.lead_researcher import research_lead
from database.database import init_db, save_lead, get_leads


def main():
    # Make sure the database exists
    init_db()

    while True:
        print("\n=== LeadGenAI ===")
        print("1. Research new lead")
        print("2. View saved leads")
        print("3. Exit")

        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            company_name = input("Company name: ").strip()
            industry = input("Industry: ").strip()
            company_info = input("What does the company do? ").strip()

            lead_info = (
                f"Company: {company_name}\n"
                f"Industry: {industry}\n"
                f"What they do: {company_info}"
            )

            print("\nResearching lead...\n")

            research = research_lead(lead_info)

            print("=== Research Result ===")
            print(research)

            save_lead(
                company_name,
                industry,
                company_info,
                research
            )

            print("\nLead saved successfully!")

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