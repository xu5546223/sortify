import json
import os
import logging

# Set up logging
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'split_dataset.log')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(log_file_path, mode='w'),
                        logging.StreamHandler()
                    ])

def split_qa_dataset(input_file_path, output_dir):
    """
    Splits the QA dataset into two files based on 'question_type': '主題級' and '細節級'.

    Args:
        input_file_path (str): The path to the input QA_dataset.json file.
        output_dir (str): The directory to save the output files.
    """
    try:
        logging.info(f"Attempting to open file: {input_file_path}")
        with open(input_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logging.info("Successfully loaded JSON data.")
    except FileNotFoundError:
        logging.error(f"Error: The file {input_file_path} was not found.")
        return
    except json.JSONDecodeError:
        logging.error(f"Error: Could not decode JSON from the file {input_file_path}.")
        return

    themed_data = []
    detailed_data = []

    for item in data:
        question_type = item.get("question_type")
        if question_type == "主題級":
            themed_data.append(item)
        elif question_type == "細節級":
            detailed_data.append(item)
    
    logging.info(f"Found {len(themed_data)} '主題級' items and {len(detailed_data)} '細節級' items.")

    themed_output_path = os.path.join(output_dir, '主題級_dataset.json')
    detailed_output_path = os.path.join(output_dir, '細節級_dataset.json')

    try:
        with open(themed_output_path, 'w', encoding='utf-8') as f:
            json.dump(themed_data, f, ensure_ascii=False, indent=2)
        logging.info(f"Successfully created {themed_output_path}")

        with open(detailed_output_path, 'w', encoding='utf-8') as f:
            json.dump(detailed_data, f, ensure_ascii=False, indent=2)
        logging.info(f"Successfully created {detailed_output_path}")

    except IOError as e:
        logging.error(f"Error writing to file: {e}")


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(script_dir, 'QA_dataset.json')
    output_directory = script_dir
    
    logging.info(f"Starting script. Reading from: {input_file}")
    split_qa_dataset(input_file, output_directory)
    logging.info("Script finished.") 