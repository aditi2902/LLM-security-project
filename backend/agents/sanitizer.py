def sanitize(analyzed_data, raw_content):
    # If the content is flagged as safe, return it
    if analyzed_data.get("safe", True):
        return raw_content
    # If not safe, surgically remove the malicious parts but keep the knowledge
    sanitized_text = raw_content
    for attack in analyzed_data.get("detected_attacks", []):
        malicious_string = attack.get("text", "")
        if malicious_string and malicious_string in sanitized_text:
            sanitized_text = sanitized_text.replace(malicious_string, "[REDACTED MALICIOUS INSTRUCTION]")
            
    return sanitized_text
