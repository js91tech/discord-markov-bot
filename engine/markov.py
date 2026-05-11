import random
import re

class MarkovChain:
    def __init__(self, order=2):
        self.order = order
        self.chain = {}

    def learn(self, text):
        words = re.findall(r'\S+', text.lower())
        if len(words) < self.order:
            return
            
        words = ["<START>"] * self.order + words + ["<END>"]
        
        for i in range(len(words) - self.order):
            key = tuple(words[i:i+self.order])
            next_word = words[i+self.order]
            
            if key not in self.chain:
                self.chain[key] = []
            self.chain[key].append(next_word)

    def generate(self, min_words=4, max_words=40, seed=None):
        if not self.chain:
            return None

        current = None
        
        # Try to use seed if provided
        if seed:
            seed_words = re.findall(r'\S+', seed.lower())
            for i in range(len(seed_words) - self.order + 1):
                test_key = tuple(seed_words[i:i+self.order])
                if test_key in self.chain:
                    current = test_key
                    break

        # If no seed or seed failed, pick a random start key
        if not current:
            start_keys = [k for k in self.chain.keys() if k[0] == "<START>"]
            current = random.choice(start_keys) if start_keys else random.choice(list(self.chain.keys()))

        output = []
        for _ in range(max_words):
            if current not in self.chain:
                break
                
            next_word = random.choice(self.chain[current])
            if next_word == "<END>":
                break
                
            output.append(next_word)
            current = tuple(list(current)[1:] + [next_word])

        if len(output) < min_words:
            return None
            
        return " ".join(output)

    def to_dict(self):
        """Converts the chain into a format safe for JSON/database storage."""
        return {str(key): value for key, value in self.chain.items()}

    def from_dict(self, data):
        """Loads the chain from the database format back into memory properly."""
        self.chain = {}
        for key_str, value in data.items():
            # Safely convert the string "(word1, word2)" back into a tuple
            clean_key = key_str.strip("()").replace("'", "").replace('"', '')
            key_tuple = tuple(k.strip() for k in clean_key.split(","))
            if len(key_tuple) == self.order:
                self.chain[key_tuple] = value
