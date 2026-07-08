from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_fund_email_system import main


if __name__ == "__main__":
    main()
