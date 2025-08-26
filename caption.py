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

caption_prompt = '''
You are a meticulous Physics Data Annotation Specialist. Your primary mission is to deconstruct multimodal physics problems (consisting of images and text) and translate them into a highly structured and comprehensive natural language description. The goal is to create a "golden" reference text that is as unambiguous and detailed as a data file, which will be used to evaluate the accuracy of other AI models. Your adherence to the format described below is critical.
You will be provided with a physics problem that consists of up to two parts: One or more **images**, and its corresponding **question text**.

### **Guiding Principles for Analysis:**
1.  **Category-First, Structure-Always:** Your entire analysis begins with correctly identifying the image's category. This category dictates the focus of your description. You must then follow the specified markdown structure precisely for your output.
2.  **Separate What is Seen from What is Inferred:** Your description must maintain a strict separation between elements explicitly visible in the diagram and properties inferred from the accompanying text (e.g., "frictionless"). The output format has dedicated sections for this.
3.  **Comprehensive and Atomic Breakdown:** Every single element in the diagram—objects, surfaces, vectors, labels, points on a graph, etc.—must be identified and described individually within the "Component Breakdown" section.
4.  **Holistic Synthesis:** The image and question text are a single unit. Use the text to define labels, understand the scenario, and extract all inferred properties.

---
### **Instructions for Structuring Your Output**
You must generate a single text block. The response must be structured using markdown with headings, bolded keywords, and bullet points exactly as specified below. For each image provided, create a complete descriptive block starting with `### Image [N]: [Category]`.

#### **Required Output Structure:**

**### Image [N]: [Primary Category Name]**
*(Replace [N] with the image number, and [Primary Category Name] with the category you identify from the list below.)*

**Scene Summary:** A single, concise sentence that describes the overall purpose and content of the diagram.

**Explicit Component Breakdown:**
*(This section is for **visible elements only**.)*
*   **[Component Name] (`[label]`):** A description of the component. The `[label]` should be the exact text or symbol labeling the component in the diagram. If there is no label, use `None`.
*   *(Repeat for every single visible component: objects, vectors, surfaces, axes, points, etc.)*

**Interactions and Relationships:**
*(This section describes how the explicit components are connected and arranged.)*
*   Describe the spatial and physical connections between components (e.g., "The block `m_1` is connected to the block `m_2` via the string.").
*   Describe the topological layout for circuits (e.g., "Resistor `R_1` is in series with the parallel branch containing `R_2` and `R_3`.").
*   Trace the path of rays for optics or describe the shape of curves for graphs.

**Implicit and Inferred Properties:**
*(This section is **only** for information derived from the question text or standard physics conventions, not explicitly drawn.)*
*   **[Component or System Name]:** [Inferred Property]. (e.g., **Inclined Plane:** The surface is frictionless.)
*   **[Component or System Name]:** [Inferred Property]. (e.g., **Connecting String:** Assumed to be massless and inextensible.)
*   *(List every piece of non-visual information.)*

**Identified Ambiguities:**
*(If any part of the image is illegible or its meaning is unclear even with context, list it here. If none, state "None.")*
*   [Description of ambiguous element].

---
### **Reference Guide: Image Categories**

*   **Mechanics Diagram:** Problems involving forces, motion, energy, and momentum (e.g., blocks, planes, pulleys, springs, pendulums).
*   **Free-Body Diagram:** An isolated diagram showing all force vectors acting on a single object.
*   **Circuit Diagram:** A diagram of an electrical circuit, including components like resistors, capacitors, inductors, and power sources.
*   **Data Plot / Graph:** A graphical representation of data, such as a velocity-time graph or a stress-strain curve.
*   **Ray Optics Diagram:** A diagram showing light rays interacting with lenses, mirrors, or other optical elements.
*   **Field Diagram:** A diagram illustrating a vector field, such as an electric or magnetic field.
*   **Thermodynamic Diagram:** A plot representing thermodynamic states and processes, such as a P-V diagram.

---
**Final Formatting Rules:**
*   Your entire output must be a single response.
*   All mathematical formulas or symbols must be wrapped in SINGLE dollar signs (e.g., `$m_1$`).
*   All LaTeX special characters inside the dollar signs MUST be escaped with TWO backslashes (e.g., `$\\theta$`).
*   Do not add any introductory or concluding text outside of the prescribed format.

Now, analyze the provided image(s) and question text, and generate the structured natural language description following this category-adaptive format.
-----
\n Original question: 
'''


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def get_item_data(item):
    question = item['question']
    image_list = item['image_path']
    return question, image_list


def inference_one_step(question, base64_images, model):
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role":
                "user",
                "content": [{
                    "type": "text",
                    "text": caption_prompt + question
                }] + [{
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    },
                } for base64_image in base64_images]
            },
        ],
    )
    return response.choices[0].message.content


def process_item(item, img_root, model):
    """
    Processes a single item dictionary. Executed by each worker thread.
    Assumes `item` contains an 'index' key.
    """
    index = item['index']

    try:
        question, image_paths = get_item_data(item)
        base64_images = [encode_image(os.path.join(img_root, img_path)) for img_path in image_paths]

        max_retries = 5
        retry_delay = 2
        attempt = 0
        response_content = None

        while attempt < max_retries:
            try:
                response_content = inference_one_step(question, base64_images, model)
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
        return {**item, "description": response_content}

    except Exception as e:
        logger.error(f"FATAL error processing item with index {index}: {e}", exc_info=True)
        # Return a structured error record, preserving the original item data
        return {**item, "description": f"ERROR: Unrecoverable failure in processing pipeline: {e}"}


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
    INPUT_JSON_PATH = 'total.json'
    OUTPUT_JSON_PATH = 'total_caption.json'
    IMAGE_ROOT_DIR = 'images'
    MODEL_NAME = 'gemini-2.5-pro'

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
