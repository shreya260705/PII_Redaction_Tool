import datetime
from typing import Dict

# Map English month names (full and abbreviated) to their calendar integer representation.
MONTH_MAP: Dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
}


def luhn_checksum_is_valid(number_str: str) -> bool:
    """
    Applies the Luhn (Modulo 10) algorithm to check if a numeric sequence is mathematically valid.
    This serves as a critical heuristic to reduce false positives for Credit Card numbers.
    """
    # Extract only digits from the input string
    digits = [int(c) for c in number_str if c.isdigit()]
    if len(digits) < 2:
        return False
    
    checksum = 0
    # Process from right to left, doubling every second digit
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            doubled = digit * 2
            checksum += doubled if doubled < 10 else doubled - 9
        else:
            checksum += digit
            
    return checksum % 10 == 0


def parse_and_validate_date(day_str: str, month_str: str, year_str: str) -> bool:
    """
    Checks if the given day, month, and year strings constitute a valid calendar date.
    Maintains leap year awareness and checks boundaries (e.g. days in February, years 1800-2100).
    """
    try:
        day = int(day_str)
        
        # Convert 2-digit years to 4-digit years (assuming 1900s for DOB if 2-digit, but standard 4-digit is preferred)
        year = int(year_str)
        if len(year_str) == 2:
            year = 1900 + year if year >= 30 else 2000 + year

        # Parse month representation
        month_str_clean = month_str.lower().strip()
        if month_str_clean.isdigit():
            month = int(month_str_clean)
        else:
            # Match first 3 letters
            month = MONTH_MAP.get(month_str_clean[:3], 0)
            if not month:
                month = MONTH_MAP.get(month_str_clean, 0)
        
        if month < 1 or month > 12:
            return False
            
        if year < 1800 or year > 2100:
            return False

        # Construct datetime date object to validate calendar mechanics (e.g., Feb 29 on non-leap years)
        datetime.date(year, month, day)
        return True
    except Exception:
        return False


def validate_ipv4(ip_str: str) -> bool:
    """
    Validates that a candidate IPv4 string consists of 4 octets, each between 0 and 255.
    """
    try:
        parts = ip_str.split('.')
        if len(parts) != 4:
            return False
        for part in parts:
            if not part.isdigit():
                return False
            # Ensure no trailing or leading whitespace, and handle standard octet ranges
            val = int(part)
            if val < 0 or val > 255:
                return False
            # Prevent single octets with excessive leading zeros like "192.168.001.0001"
            if len(part) > 1 and part.startswith('0') and int(part) != 0:
                # Octets like '01' are technically parsed, but let's be strict or allow it.
                # Standard IP parsing allows it, but to prevent false positives, we can keep it flexible.
                pass
        return True
    except Exception:
        return False
