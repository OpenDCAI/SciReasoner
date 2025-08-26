import base64
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from os.path import exists
from openai import OpenAI
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def build_prompt_answer(item):
    question = item['question']
    description = item['description']

    prompt = '''
You are an expert Physics Problem Solver and Educator. Your task is to solve a physics problem based on a structured description of its visual and textual components. You must not only find the correct answer but also present your solution in a clear, logical, and pedagogically sound manner that demonstrates a deep understanding of the underlying principles.
You will be provided with the structured **Image(s)**, **Image Description** and the **Question**.

**Format your output as follows:**
- Step-by-Step Solution
- Final Answer

---
### **Final Answer Formatting Guide**

The format of the content inside `\\boxed{}` must match the type of answer demanded by the question.
*   **For a Single Value:** Place the single number, symbol, or formula in the box.
    *   Example: `\\boxed{4.9 \\, \\text{m/s}^2}` or `\\boxed{\\frac{m h}{M+m}\\cot\\theta}`

*   **For Multi-Part Answers:** If the question asks for several quantities (e.g., "the spins and parities," or "the force and torque"), list them separated by commas within a *single* `\\boxed{}`.
    *   Example: `\\boxed{-1.91 \\mu_{N}, 5.79 \\mu_{N}, -1.14 \\times 10^{-25} \\mathrm{~cm}^{2}}`

*   **For Conditional Answers:** If the answer depends on different conditions or cases, write out the cases explicitly inside a *single* `\\boxed{}`.
    *   Example: `\\boxed{\\text{Case (i): For } ka < \\frac{Mg}{2} \\text{ the equilibrium is at } \\theta=0 \\text{ (unstable) and } \\theta=\\pi \\text{ (stable). Case (ii): ...}}`

*   **For Piecewise Functions:** Use the LaTeX `cases` environment inside the `\\boxed{}`.
    *   Example: `\\boxed{V(r)=\\begin{cases} \\frac{Q}{4\\pi a(\\alpha a+1)}, & r \\le a \\\\ \\frac{Qe^{\\alpha a}e^{-\\alpha r}}{4\\pi(\\alpha a+1)r}, & r > a \\end{cases}}`

*   **For Qualitative Answers:** Place the concise, definitive text inside the box.
    *   Example: `\\boxed{\\text{Bulbs 1 and 3 only}}`

*   **For Vector Answers:** Use standard vector notation.
    *   Example: `\\boxed{\\mathbf{J}_{EM}=\\frac{qB_{0}(b^{2}-a^{2})}{2}\\,\\mathbf{e}_{z}}`

---
**Overall Formatting Rules:**
*   All mathematical formulas must be wrapped in SINGLE dollar signs (`$...$`).
*   All LaTeX special characters inside the dollar signs MUST be escaped with TWO backslashes (e.g., `\\theta`, `\\frac`).

---
    '''
    prompt += '\n Image Description: ' + description
    prompt += '\n Question: ' + question

    if item['sig_figs']:
        sf = str(int(item['sig_figs']))
        prompt += f"\n The final answer MUST retain {sf} significant figures."

    return prompt


def build_prompt_critic(item):
    question = item['question']
    description = item['description']
    prediction = item['prediction']
    prompt = '''
**You are an expert physicist. Your task is to meticulously review the provided solution to the following physics problem and determine its correctness. You must analyze the application of physical principles, the mathematical steps, and the handling of units.**

**The Problem, the Image(s), the Image Description and Proposed Solution are provided:**
''' + '\n Image Description:' + description + '\n Question: ' + question + "\n **Proposed Solution to be Evaluated:** " + prediction + '''

**Your Evaluation and Response:**

**If the Proposed Solution is entirely correct (in its physical reasoning, mathematical calculations, and unit handling):**

* Your output should be:
    "The provided solution is correct. The final answer is: [Insert the original final answer here]"

**If the Proposed Solution is incorrect at any point:**

* Your output must:
    1.  Begin with the statement: "The provided solution is incorrect."
    2.  Clearly identify and explain the error(s) in the proposed solution. Be specific about whether the error is conceptual (e.g., using the wrong formula), mathematical (e.g., a calculation mistake), or related to units.
    3.  Provide a detailed, step-by-step corrected solution, showing the correct application of principles and calculations.
    4.  Conclude with the final correct answer, clearly stated and with the proper units. For example: "The final correct answer is: [Your calculated correct answer with units]"

**Do not deviate from these instructions.**

---
### **Final Answer Formatting Guide**

The format of the content inside `\\boxed{}` must match the type of answer demanded by the question.
*   **For a Single Value:** Place the single number, symbol, or formula in the box.
    *   Example: `\\boxed{4.9 \\, \\text{m/s}^2}` or `\\boxed{\\frac{m h}{M+m}\\cot\\theta}`

*   **For Multi-Part Answers:** If the question asks for several quantities (e.g., "the spins and parities," or "the force and torque"), list them separated by commas within a *single* `\\boxed{}`.
    *   Example: `\\boxed{-1.91 \\mu_{N}, 5.79 \\mu_{N}, -1.14 \\times 10^{-25} \\mathrm{~cm}^{2}}`

*   **For Conditional Answers:** If the answer depends on different conditions or cases, write out the cases explicitly inside a *single* `\\boxed{}`.
    *   Example: `\\boxed{\\text{Case (i): For } ka < \\frac{Mg}{2} \\text{ the equilibrium is at } \\theta=0 \\text{ (unstable) and } \\theta=\\pi \\text{ (stable). Case (ii): ...}}`

*   **For Piecewise Functions:** Use the LaTeX `cases` environment inside the `\\boxed{}`.
    *   Example: `\\boxed{V(r)=\\begin{cases} \\frac{Q}{4\\pi a(\\alpha a+1)}, & r \\le a \\\\ \\frac{Qe^{\\alpha a}e^{-\\alpha r}}{4\\pi(\\alpha a+1)r}, & r > a \\end{cases}}`

*   **For Qualitative Answers:** Place the concise, definitive text inside the box.
    *   Example: `\\boxed{\\text{Bulbs 1 and 3 only}}`

*   **For Vector Answers:** Use standard vector notation.
    *   Example: `\\boxed{\\mathbf{J}_{EM}=\\frac{qB_{0}(b^{2}-a^{2})}{2}\\,\\mathbf{e}_{z}}`

---
**Overall Formatting Rules:**
*   All mathematical formulas must be wrapped in SINGLE dollar signs (`$...$`).
*   All LaTeX special characters inside the dollar signs MUST be escaped with TWO backslashes (e.g., `\\theta`, `\\frac`).

---
    '''
    if item['sig_figs']:
        sf = str(int(item['sig_figs']))
        prompt += f"\n The final answer MUST retain {sf} significant figures."

    return prompt


def inference_one_step(prompt, base64_images, model):
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role":
                "user",
                "content": [{
                    "type": "text",
                    "text": prompt
                }] + [{
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    },
                } for base64_image in base64_images]
            },
        ],
    )

    response = response.choices[0].message.content
    return response


def process_item(item, img_root, model):
    """
    Processes a single item dictionary. Executed by each worker thread.
    Assumes `item` contains an 'index' key.
    """
    index = item['index']

    try:
        image_paths = item['image_path']
        prompt = build_prompt_answer(item)
        base64_images = [encode_image(os.path.join(img_root, img_path)) for img_path in image_paths]

        max_retries = 5
        retry_delay = 2
        attempt = 0
        response_content = None

        while attempt < max_retries:
            try:
                response_content = inference_one_step(prompt, base64_images, model)
                break  # Success
            except Exception as e:
                attempt += 1
                logger.error(f"Index {index} | Attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)  # Exponential backoff
                else:
                    logger.error(f"Index {index} | Max retries reached. Marking as error.")
                    response_content = f"ERROR: Max retries reached - {e}"
        # Return a new dictionary with the original item's data plus the new description
        return {**item, "prediction": response_content}

    except Exception as e:
        logger.error(f"FATAL error processing item with index {index}: {e}", exc_info=True)
        # Return a structured error record, preserving the original item data
        return {**item, "prediction": f"ERROR: Unrecoverable failure in processing pipeline: {e}"}


def run_inference_concurrent(
    json_path,
    output_path,
    img_root,
    model='gpt-4o',
    max_workers=4,
):
    # 1. Load the full dataset.
    # Assumes the input JSON is a list of objects, each with a unique 'index' key.
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            full_dataset = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load or parse input file {json_path}: {e}")
        return

    # 2. Implement breakpoint resume capability.
    existing_results = []
    if exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_results = json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Output file {output_path} is corrupted. Starting fresh.")

    # Use the 'index' key from the data to identify completed items.
    completed_indices = {item.get('index') for item in existing_results if isinstance(item.get('index'), int)}
    items_to_process = [item for item in full_dataset if item.get('index') not in completed_indices]

    if not items_to_process:
        logger.info("All items have been processed according to the output file. Exiting.")
        return

    logger.info(f"Total items in dataset: {len(full_dataset)}")
    logger.info(f"Items already processed: {len(completed_indices)}")
    logger.info(f"Items remaining to process: {len(items_to_process)}")

    # 3. Process remaining items concurrently.
    new_results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(process_item, item, img_root, model): item for item in items_to_process}

        progress = tqdm(as_completed(future_to_item), total=len(items_to_process), desc="Processing Items")
        for future in progress:
            try:
                result = future.result()
                if result:
                    new_results.append(result)
            except Exception as e:
                item = future_to_item[future]
                logger.error(f"A task for index {item.get('index')} raised an unhandled exception: {e}")

    # 4. Merge, sort, and save results.
    if new_results:
        combined_results = existing_results + new_results

        # Sort by the pre-existing 'index' key to ensure original order.
        combined_results.sort(key=lambda x: x.get('index', float('inf')))

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(combined_results, f, ensure_ascii=False, indent=4)
        logger.info(f"Processing complete. Saved {len(combined_results)} total items to {output_path}.")
    else:
        logger.info("No new items were processed in this run.")


if __name__ == '__main__':
    # Define execution parameters
    MAX_CONCURRENT_WORKERS = 16
    INPUT_JSON_PATH = 'total_caption.json'
    OUTPUT_JSON_PATH = 'prediction.json'
    IMAGE_ROOT_DIR = 'images'
    MODEL_NAME = 'o3'

    client = OpenAI(
        base_url="",
        api_key="",
    )

    # Run the main function
    run_inference_concurrent(json_path=INPUT_JSON_PATH,
                             output_path=OUTPUT_JSON_PATH,
                             img_root=IMAGE_ROOT_DIR,
                             model=MODEL_NAME,
                             max_workers=MAX_CONCURRENT_WORKERS)
