from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
import os
from typing import List, Dict
from PyPDF2 import PdfReader
import re
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

def get_transcript(video_id: str, preferred_langs: List[str] = ['en']) -> Dict:
    """Get transcript with fallback languages and translation"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to get transcript in preferred languages
        transcript = None
        used_language = None
        
        # First try manual transcripts
        for lang in preferred_langs:
            try:
                if lang in transcript_list._manually_created_transcripts:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    used_language = lang
                    break
            except:
                continue
        
        # If no manual transcript, try auto-generated
        if not transcript:
            for lang in preferred_langs:
                try:
                    if lang in transcript_list._generated_transcripts:
                        transcript = transcript_list.find_generated_transcript([lang])
                        used_language = lang
                        break
                except:
                    continue
        
        # If still no transcript, get the first available auto-generated one
        if not transcript and transcript_list._generated_transcripts:
            lang = list(transcript_list._generated_transcripts.keys())[0]
            transcript = transcript_list.find_generated_transcript([lang])
            used_language = lang
        
        # If we found a transcript
        if transcript:
            # Translate to English if needed
            if used_language != 'en':
                try:
                    transcript = transcript.translate('en')
                    used_language = 'en (translated)'
                except Exception as e:
                    print(f"Translation failed: {str(e)}")
            
            transcript_data = transcript.fetch()
            
            # Return the raw transcript segments
            segments = []
            for entry in transcript_data:
                segments.append({
                    'start': entry['start'],
                    'text': entry['text']
                })
            
            return {
                'success': True,
                'segments': segments,
                'language': used_language
            }
        
        return {'success': False, 'error': 'No transcript available'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/')
def index():
    return render_template('youtube.html')

@app.route('/api/process_video', methods=['POST'])
def process_video():
    try:
        data = request.get_json()
        video_id = data.get('video_id')
        
        if not video_id:
            return jsonify({'error': 'No video ID provided'}), 400
        
        # Get transcript
        transcript_result = get_transcript(video_id)
        
        if not transcript_result['success']:
            return jsonify({'error': transcript_result['error']}), 400
        
        return jsonify({
            'success': True,
            'segments': transcript_result['segments'],
            'language': transcript_result['language']
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/api/get_word_meaning', methods=['POST'])
def get_word_meaning():
    try:
        # Parse the word from the request
        data = request.get_json()
        word = data.get('word')
        if not word:
            return jsonify({'error': 'No word provided'}), 400

        # Use Gemini API to fetch the meaning and usage
        import google.generativeai as genai
        genai.configure(api_key="AIzaSyAlr__Kff7n4tDrJoEhmx471Ek-u78E3B0")  # Replace with your actual Gemini API key

        # Create the prompt for Gemini
        prompt = f"Provide a brief definition and a simple example sentence for the word '{word}'. Format the response as: Definition: [brief definition] Example: [example sentence]"

        # Generate response using Gemini
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        
        # Parse the response
        response_text = response.text
        definition_part = response_text.split("Example:")[0].replace("Definition:", "").strip()
        example_part = response_text.split("Example:")[1].strip() if "Example:" in response_text else "No example available."

        return jsonify({
            'meaning': definition_part,
            'usage': example_part
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/api/generate_notes', methods=['POST'])
def generate_notes():
    try:
        data = request.get_json()
        content = data.get('content')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400

        import google.generativeai as genai
        genai.configure(api_key="AIzaSyAlr__Kff7n4tDrJoEhmx471Ek-u78E3B0")
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        Analyze the following content and provide:
        1. Key points (as HTML bullet points)
        2. A concise summary (2-3 paragraphs)
        
        Format the response as:
        Key Points:
        <ul>[points as li elements]</ul>
        
        Summary:
        [summary paragraphs]
        
        Content to analyze:
        {content}
        """
        
        response = model.generate_content(prompt)
        
        # Split response into key points and summary
        parts = response.text.split('Summary:')
        key_points = parts[0].replace('Key Points:', '').strip()
        summary = parts[1].strip() if len(parts) > 1 else "Summary not available."
        
        return jsonify({
            'key_points': key_points,
            'summary': summary
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/api/process_pdf', methods=['POST'])
def process_pdf():
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'No PDF file provided'}), 400

        pdf_file = request.files['pdf_file']
        if pdf_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'File must be a PDF'}), 400

        # Create a PDF reader object
        pdf_reader = PdfReader(pdf_file)
        
        # Extract text from all pages
        text_content = []
        for page in pdf_reader.pages:
            text_content.append(page.extract_text())

        # Join all pages' text
        full_text = '\n'.join(text_content)

        return jsonify({
            'success': True,
            'content': full_text
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    
@app.route('/api/search_pdf', methods=['POST'])
def search_pdf():
    try:
        data = request.get_json()
        content = data.get('content', '')
        query = data.get('query', '').strip()

        if not content or not query:
            return jsonify({'error': 'Content and query are required'}), 400

        # Split content into paragraphs and remove empty lines
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        # Search for matches with context
        results = []
        query_terms = query.lower().split()
        
        for paragraph in paragraphs:
            # Check if all search terms are in the paragraph
            if all(term.lower() in paragraph.lower() for term in query_terms):
                # Clean up the paragraph
                clean_paragraph = ' '.join(paragraph.split())
                
                # Find the position of each term for context
                term_positions = []
                for term in query_terms:
                    pos = clean_paragraph.lower().find(term.lower())
                    if pos != -1:
                        term_positions.append(pos)
                
                # Get a window of text around the first occurrence
                if term_positions:
                    start_pos = max(0, min(term_positions) - 100)
                    end_pos = min(len(clean_paragraph), max(term_positions) + 100)
                    
                    # Ensure we don't cut words in half
                    if start_pos > 0:
                        start_pos = clean_paragraph.find(' ', start_pos) + 1
                    if end_pos < len(clean_paragraph):
                        end_pos = clean_paragraph.rfind(' ', 0, end_pos)
                    
                    context = clean_paragraph[start_pos:end_pos]
                    
                    # Add ellipsis if we're not at the start/end
                    if start_pos > 0:
                        context = f"...{context}"
                    if end_pos < len(clean_paragraph):
                        context = f"{context}..."
                    
                    results.append({
                        'text': context,
                        'full_paragraph': clean_paragraph,
                        'matches': query_terms
                    })

        return jsonify({
            'success': True,
            'results': results[:10],  # Limit to top 10 results
            'total_matches': len(results)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

# Add this to your Flask routes
@app.route('/api/process_text_search', methods=['POST'])
def process_text_search():
    try:
        data = request.get_json()
        content = data.get('content', '')
        query = data.get('query', '').strip()

        if not content or not query:
            return jsonify({'error': 'Content and query are required'}), 400

        # Split content into sentences
        sentences = [s.strip() for s in re.split('[.!?]+', content) if s.strip()]
        
        # Search for matches
        matching_sentences = []
        query_terms = query.lower().split()
        
        for sentence in sentences:
            if all(term.lower() in sentence.lower() for term in query_terms):
                matching_sentences.append(sentence)

        if not matching_sentences:
            return jsonify({
                'success': True,
                'results': [],
                'total_matches': 0
            })

        # Use Gemini to combine and enhance the matching sentences
        import google.generativeai as genai
        genai.configure(api_key="AIzaSyAlr__Kff7n4tDrJoEhmx471Ek-u78E3B0")
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        Combine and enhance these related sentences into a coherent paragraph, maintaining all key information:
        {' '.join(matching_sentences)}
        
        Requirements:
        1. Maintain all factual information from the original sentences
        2. Improve flow and readability
        3. Add transitional phrases where needed
        4. Keep the same meaning and context
        """
        
        response = model.generate_content(prompt)
        enhanced_paragraph = response.text.strip()

        return jsonify({
            'success': True,
            'results': [{
                'original_sentences': matching_sentences,
                'enhanced_paragraph': enhanced_paragraph,
                'matches': query_terms
            }],
            'total_matches': len(matching_sentences)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Run on port 5001 instead of default 5000
    app.run(host='0.0.0.0', port=8000, debug=True)