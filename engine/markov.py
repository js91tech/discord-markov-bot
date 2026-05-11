import random
import re
import json

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
        
        if seed:
            seed_words = re.findall(r'\S+', seed.lower())
            for i in range(len(seed_words) - self.order + 1):
                test_key = tuple(seed_words[i:i+self.order])
                if test_key in self.chain:
                    current = test_key
                    break

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

    def to_db_dict(self):
        """Safely converts the chain into a dictionary of JSON strings for SQLite."""
        db_dict = {}
        for key_tuple, values in self.chain.items():
            # Convert the tuple ('word1', 'word2') into a JSON string '["word1", "word2"]'
            json_key = json.dumps(list(key_tuple))
            db_dict[json_key] = values
        return db_dict

    def from_db_dict(self, db_dict):
        """Safely loads the chain from the database JSON strings back into tuples."""
        self.chain = {}
        for json_key, values in db_dict.items():
            # Convert '["word1", "word2"]' back into a Python tuple ('word1', 'word2')
            key_list = json.loads(json_key)
            key_tuple = tuple(key_list)
            if len(key_tuple) == self.order:
                self.chain[key_tuple] = values
