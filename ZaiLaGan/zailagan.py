from typing import *
import torch
from transformers import BertTokenizer, BertForMaskedLM
from zhon import hanzi
from utilities.utils import Utils

class ZaiLaGan():
  # Initialize config, device, model, tokenizer, and utilities
  def __init__(self, config):
    self.config = config
    self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    self.bert_wwm_model = BertForMaskedLM.from_pretrained(self.config["Model"]["bert_wwm_ext_chinese"])
    self.bert_wwm_model.eval()
    self.bert_wwm_model = self.bert_wwm_model.to(self.device)
    self.bert_wwm_tokenizer = BertTokenizer.from_pretrained(self.config["Model"]["bert_wwm_ext_chinese"])
    self.utils = Utils(self.config)
    self.pinyin = self.utils.loadPinYin(self.config["Data"]["pinyin"])
    self.stroke = self.utils.loadStroke(self.config["Data"]["stroke"])
    self.dict_trie = self.utils.loadDictionaryTrie(self.config["Data"]["dictionary"], True)

  # Detect potential spelling errors in a given sentence/paragraph and return detected error positions
  def detectSpellingError(self, text: str, threshold: float) -> List[int]:
    positions = []
    # Mask each word and predict it
    for i in range(len(text)):
      # Check if current word is a punctuation
      if(text[i] in hanzi.punctuation):
        continue
      # Add mask
      masked_text = "[CLS]" + text[:i] + "[MASK]" + text[i+1:] + "[SEP]"
      # Tokenize input text
      tokenized_masked_text = self.bert_wwm_tokenizer.tokenize(masked_text)
      # Construct token ids and segment ids
      token_ids = torch.tensor([self.bert_wwm_tokenizer.convert_tokens_to_ids(tokenized_masked_text)])
      segment_ids = torch.tensor([[0] * token_ids.shape[1]])
      # Set up ids on GPU
      token_ids = token_ids.to(self.device)
      segment_ids = segment_ids.to(self.device)
      # Predict masked token
      with torch.no_grad():
        outputs = self.bert_wwm_model(token_ids, token_type_ids = segment_ids)
        scores = outputs[0][0,i+1]
        token_probability = torch.nn.Softmax(0)(scores)[self.bert_wwm_tokenizer.convert_tokens_to_ids(text[i])]
        # Classify the token as a potential spelling error if predicted probability is lower than given threshold
        if(token_probability < threshold):
          positions.append(i)
    return positions

  # Give top n suggestions of spelling error correction
  def correctSpellingError(self, text: str, err_positions: List[int], ne_positions: List[int], candidate_num: int) -> List[str]:
    # Convert error positions and named-entity positions into sets
    err_positions = set(err_positions)
    ne_positions = set(ne_positions)
    # Initialize a dictionary to record starting positions of potentially correct tokens/words
    starting_positions = {}
    # Add original tokens
    for i in range(len(text)):
      token = text[i]
      starting_positions[i] = [token]
    # Add similar tokens in stroke or pinyin
    for error_position in err_positions:
      error_token = text[error_position]
      # Check if the error token is included in a named-entity
      if(error_position in ne_positions):
        continue
      else:
        if(error_token in self.stroke):
          for similar_token in self.stroke[error_token]:
            starting_positions[error_position].append(similar_token)
        if(error_token in self.pinyin):
          for similar_token in self.pinyin[error_token]:
            starting_positions[error_position].append(similar_token)
    # Construct candidate sentences
    candidates = []
    prefixes = starting_positions[0].copy()
    while(len(prefixes) > 0):
      prefix = prefixes.pop(0)
      if(len(prefix) == len(text)):
        candidates.append((prefix,self.utils.getSentencePpl(prefix)))
      else:
        for suffix in starting_positions[len(prefix)]:
          prefixes.append(prefix+suffix)
    # Sort candidate sentences by perplexity and get top n suggestions
    candidates.sort(key = lambda x: x[1])
    recommendations = []
    for i in range(min(len(candidates),candidate_num)):
      recommendations.append(candidates[i][0])
    return recommendations   