import json
import os
from agents.trust_analyzer import analyze_trust

def load_dataset(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return []

def run_evaluation():
    datasets = [
        ("dataset/safe.json", "SAFE"),
        ("dataset/attacks.json", "PROMPT_INJECTION"),
        ("dataset/manipulation.json", "MANIPULATION")
    ]
    
    total = 0
    correct = 0
    
    for filepath, expected_label in datasets:
        data = load_dataset(filepath)
        for sample in data:
            total += 1
            text = sample['text']
            result = analyze_trust(text)
            
            # Simple heuristic mapping the risk_score/categories to our labels
            risk_score = result.get('risk_score', 0)
            instructions = result.get('instructions', [])
            manipulation = result.get('manipulation', [])
            
            predicted_label = "SAFE"
            if risk_score > 70 or len(manipulation) > 0:
                if "ignore" in text.lower() or "hack" in text.lower():
                    predicted_label = "PROMPT_INJECTION"
                else:
                    predicted_label = "MANIPULATION"
            
            if predicted_label == expected_label:
                correct += 1
            else:
                print(f"Mismatch! Text: {text[:30]}... Expected: {expected_label}, Predicted: {predicted_label}, Risk: {risk_score}")
                
    accuracy = correct / total if total > 0 else 0
    print(f"\\nEvaluation Complete! Accuracy: {accuracy * 100:.2f}% ({correct}/{total})")

if __name__ == "__main__":
    run_evaluation()
