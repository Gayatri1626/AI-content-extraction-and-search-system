import requests
from bs4 import BeautifulSoup
from transformers import pipeline
import textwrap

# Function to fetch text from a URL
def fetch_text_from_url(url):
    # Send HTTP request to the URL
    response = requests.get(url)
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract text from the page
        text = soup.get_text()
        
        return text
    else:
        return "Failed to retrieve content from the URL."

# Function to summarize text using Hugging Face's summarization model
def summarize_text(text, chunk_size=1000):
    # Load the summarization pipeline from Hugging Face
    summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
    
    # Split the text into chunks of chunk_size characters
    chunks = textwrap.wrap(text, chunk_size)
    
    # Initialize a list to hold the summarized chunks
    summaries = []
    
    for chunk in chunks:
        # Calculate a max_length based on the chunk length
        # Ensure max_length is smaller than input_length
        max_length = max(50, len(chunk) // 2)  # Dynamic max_length, at least 50 characters
        
        # Generate summary for each chunk
        summary = summarizer(chunk, max_length=max_length, min_length=50, do_sample=False)
        summaries.append(summary[0]['summary_text'])
    
    # Join all summaries together
    return " ".join(summaries)

# Function to save fetched text and summary to a text file with bullet points
def save_to_file(fetched_text, summary, file_name="summary_output.txt"):
    with open(file_name, 'w', encoding='utf-8') as f:
        f.write("Fetched Text:\n")
        f.write(fetched_text)
        f.write("\n\nSummary:\n")
        
        # Split summary into sentences for better readability
        summary_sentences = summary.split('. ')
        
        # Add bullet points to each sentence in the summary
        for sentence in summary_sentences:
            f.write(f"• {sentence.strip()}\n")
    
    print(f"Data has been saved to {file_name}")

# Example URL (replace with your desired link)
url = "https://www.ibm.com/think/topics/chatbots"
text = fetch_text_from_url(url)

# Summarize the fetched text if the text is available
if text and text != "Failed to retrieve content from the URL.":
    summary = summarize_text(text)
    print("Summary:")
    print(summary)
    
    # Save the fetched text and summary to a file
    save_to_file(text, summary)
else:
    print(text)
