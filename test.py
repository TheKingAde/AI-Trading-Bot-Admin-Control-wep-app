import csv

def write_clean_trade_header(filename="clean_trades1.csv"):
    with open(filename, mode="w", newline='', encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=';')

        header = []

        # === TRADE IDENTIFICATION ===
        header += ["Trade_Time", "Symbol", "Action"]

        # === TRADE EXECUTION ===
        header += ["Entry", "Exit_Price", "SL", "TP"]

        # === BREAKOUT QUALITY ===
        header += ["Breakout_Strength"]

        # === BREAKOUT TIME & SESSION ===
        header += [
            "Hour_of_Day", "Day_of_Week",
            "Is_London_Session", "Is_NY_Session", "Is_Asian_Session"
        ]

        # === 7 H1 CANDLES BEFORE BREAKOUT ===
        for i in range(1, 8):
            header += [
                f"C{i}_Open", f"C{i}_High", f"C{i}_Low", f"C{i}_Close",
                f"C{i}_BodyPts", f"C{i}_UpperWickPts", f"C{i}_LowerWickPts"
            ]

        # === OUTCOMES ===
        header += ["Win", "Profit", "Profit_Pct", "Outcome"]

        # Write to file
        writer.writerow(header)

    print(f"✅ Header written successfully to {filename}")

if __name__ == "__main__":
    write_clean_trade_header()
