# Captioner & Reasoner: Multimodal Problem Solver Pipeline



This repository contains a sophisticated, multi-stage pipeline for solving physics problems that involve both text and images. The core strategy is to decompose the complex task of problem-solving into distinct stages: first, understanding and describing the problem in a structured way, and then reasoning through that description to find a solution.

This workflow employs a powerful **Describe-Answer-Critique & Refine** model:

1. **Generate Descriptions (`caption.py`):** An AI model analyzes the problem and generates a detailed, structured textual description.
2. **Generate Initial Solution (`answer.py`, 1st pass):** A second AI prompt uses the structured description to generate a preliminary answer.
3. **Critique & Refine Solution (`answer.py`, 2nd pass):** A third AI prompt acts as an expert critic, reviewing the initial solution for errors and providing a corrected, final answer.



## Workflow Overview



The process relies on a chain of scripts and data files:

```
[total.json] --> python caption.py --> [total_caption.json] --> python answer.py (Pass 1) --> [prediction.json] --> (Manual Edit) --> python answer.py (Pass 2) --> [final_prediction.json]
```



## Prerequisites



1. **Python 3**: Ensure you have a working Python 3 environment.

2. **Required Libraries**: Install the necessary Python libraries.

   ```bash
   pip install openai tqdm
   ```

3. **API Key**: This pipeline requires an API key from a provider like OpenAI. You must set your credentials within each script (`caption.py` and `answer.py`).

   ```python
   # Inside both answer.py and caption.py
   client = OpenAI(
       base_url="YOUR_API_BASE_URL", # Or leave empty
       api_key="YOUR_API_KEY",      # Replace with your actual key
   )
   ```

   

## Step-by-Step Instructions



Follow these three stages to get the final, refined answers.



### Stage 1: Generate Structured Descriptions



This stage uses `caption.py` to analyze your problems and create detailed descriptions.

1. **Configure `caption.py`**:

   - Ensure `INPUT_JSON_PATH` is set to `'total.json'`.
   - Ensure `OUTPUT_JSON_PATH` is set to `'total_caption.json'`.
   - The model is set to `gemini-2.5-pro` by default. You can change `MODEL_NAME` if needed.

2. **Run the script**:

   ```bash
   python caption.py
   ```

3. **Output**: A new file, `total_caption.json`, will be created. It contains your original data plus a new `description` field for each problem.



### Stage 2: Generate Initial Answers



This stage runs `answer.py` in its default mode to generate the first draft of the solutions.

1. **Configure `answer.py`**:

   - Ensure `INPUT_JSON_PATH` is set to `'total_caption.json'`.
   - Ensure `OUTPUT_JSON_PATH` is set to `'prediction.json'`.
   - By default, the script will use the `build_prompt_answer` function, which prompts the AI to act as a "Physics Problem Solver and Educator".

2. **Run the script**:

   ```bash
   python answer.py
   ```

3. **Output**: A new file, `prediction.json`, will be created. It contains the data from the previous step plus a new `prediction` field holding the initial solution.



### Stage 3: Critique and Refine Answers



This final stage re-runs `answer.py` in a "critic" mode to review and correct the initial answers. This requires a **manual code modification**.

1. **Manually Edit `answer.py`**:

   - Change the input and output file paths to avoid overwriting your data. For example:

     ```python
     # In answer.py
     INPUT_JSON_PATH = 'prediction.json'
     OUTPUT_JSON_PATH = 'final_prediction.json' # Use a new name for the final output
     ```

   - Modify the `process_item` function to call `build_prompt_critic` instead of `build_prompt_answer`. This changes the AI's role to an expert reviewer.

     **Before modification:**

     ```python
     # Inside the process_item function in answer.py
     prompt = build_prompt_answer(item) 
     ```

     **After modification:**

     ```python
     # Inside the process_item function in answer.py
     prompt = build_prompt_critic(item)
     ```

2. **Run the modified script**:

   ```bash
   python answer.py
   ```

3. **Final Output**: The file `final_prediction.json` (or your chosen output name) will be generated. The `prediction` field in this file will contain the critiqued and potentially corrected final answer, including an explanation if the initial solution was wrong.



## Configuration



You can adjust the performance of the scripts by changing the constants at the bottom of each file:

- `MAX_CONCURRENT_WORKERS`: The number of parallel threads to run for processing.
- `INPUT_JSON_PATH`: The source data file.
- `OUTPUT_JSON_PATH`: The destination for the results.
- `IMAGE_ROOT_DIR`: The directory where images are stored.
- `MODEL_NAME`: The specific AI model to be used for the task.