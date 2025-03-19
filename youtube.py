from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
import google.generativeai as genai
import os
from typing import List, Dict, Optional
import json
from datetime import datetime

class TranscriptError(Exception):
    """Custom exception for transcript-related errors"""
    pass

class YouTubeTranscriptAnalyzer:
    def __init__(self, gemini_api_key: str):
        """
        Initialize the analyzer with Gemini API credentials
        Args:
            gemini_api_key (str): API key for Google's Gemini API
        """
        self.gemini_api_key = gemini_api_key
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        
    def get_video_id(self, url: str) -> Optional[str]:
        """
        Extract video ID from YouTube URL
        Args:
            url (str): YouTube video URL
        Returns:
            str: Video ID if found, None otherwise
        """
        parsed_url = urlparse(url)
        if parsed_url.hostname == 'youtu.be':
            return parsed_url.path[1:]
        if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed_url.path == '/watch':
                return parse_qs(parsed_url.query)['v'][0]
            if parsed_url.path[:7] == '/embed/':
                return parsed_url.path.split('/')[2]
            if parsed_url.path[:3] == '/v/':
                return parsed_url.path.split('/')[2]
        return None

    def get_available_transcripts(self, video_id: str) -> Dict:
        """
        Get list of available transcript languages
        Args:
            video_id (str): YouTube video ID
        Returns:
            dict: Dictionary containing manual and generated transcript languages
        """
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            return {
                'manual': [t.language_code for t in transcript_list._manually_created_transcripts.values()],
                'generated': [t.language_code for t in transcript_list._generated_transcripts.values()]
            }
        except Exception as e:
            return {'error': f"Error getting transcript list: {str(e)}"}

    def get_transcript(self, video_id: str, preferred_langs: List[str] = ['en', 'hi']) -> Dict:
        """
        Get transcript with fallback languages and translation
        Args:
            video_id (str): YouTube video ID
            preferred_langs (list): List of preferred language codes
        Returns:
            dict: Transcript data including text, segments, and language
        """
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
                
                return {
                    'text': ' '.join([entry['text'] for entry in transcript_data]),
                    'segments': transcript_data,
                    'language': used_language
                }
            
            return {'error': 'No transcript available'}
            
        except Exception as e:
            return {'error': f"Error getting transcript: {str(e)}"}

    def analyze_text(self, text: str, word: str) -> Dict:
        """
        Analyze text using Gemini API to get information about specific word
        Args:
            text (str): Text to analyze
            word (str): Word to analyze
        Returns:
            dict: Analysis results including word information and context
        """
        try:
            prompt = f"""
            Analyze the following text and provide:
            1. 3-4 clear, concise sentences about how the word '{word}' is used and its context
            2. Frequency of the word's appearance
            3. Key themes or topics associated with the word
            4. Any significant collocations or phrases where the word appears

            Make the response informative but concise.

            Text to analyze: {text}
            """
            
            response = self.model.generate_content(prompt)
            return {
                'word': word,
                'analysis': response.text,
                'timestamp': datetime.now().isoformat(),
                'success': True
            }
        except Exception as e:
            return {
                'word': word,
                'error': f"Error analyzing text: {str(e)}",
                'timestamp': datetime.now().isoformat(),
                'success': False
            }

    def analyze_multiple_words(self, text: str, words: List[str]) -> Dict:
        """
        Analyze multiple words in the text
        Args:
            text (str): Text to analyze
            words (list): List of words to analyze
        Returns:
            dict: Analysis results for each word
        """
        results = {}
        for word in words:
            results[word] = self.analyze_text(text, word)
        return results

    def process_video_with_analysis(
        self, 
        url: str, 
        target_words: List[str],
        output_file: str = None
    ) -> Dict:
        """
        Process YouTube video, extract transcript, and analyze specific words
        Args:
            url (str): YouTube video URL
            target_words (list): List of words to analyze
            output_file (str, optional): Output file path
        Returns:
            dict: Complete analysis results
        """
        # Get video ID
        video_id = self.get_video_id(url)
        if not video_id:
            return {'error': 'Invalid YouTube URL'}
        
        # Get transcript
        transcript_result = self.get_transcript(video_id)
        if 'error' in transcript_result:
            return transcript_result
        
        # Analyze the words
        analysis_results = self.analyze_multiple_words(transcript_result['text'], target_words)
        
        # Generate output filename if not provided
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"youtube_analysis_{timestamp}.txt"
        
        # Save results to file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"YOUTUBE VIDEO TRANSCRIPT ANALYSIS\n")
                f.write(f"================================\n\n")
                f.write(f"Video URL: {url}\n")
                f.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Transcript Language: {transcript_result['language']}\n\n")
                
                f.write("WORD ANALYSIS\n")
                f.write("=============\n\n")
                for word, analysis in analysis_results.items():
                    f.write(f"Word: {word}\n")
                    f.write("-" * (len(word) + 6) + "\n")
                    if analysis['success']:
                        f.write(analysis['analysis'])
                    else:
                        f.write(f"Error: {analysis['error']}")
                    f.write("\n\n")
                
                f.write("FULL TRANSCRIPT\n")
                f.write("===============\n\n")
                f.write(transcript_result['text'])
                
                # Save timestamped segments
                f.write("\n\nTIMESTAMPED SEGMENTS\n")
                f.write("===================\n\n")
                for segment in transcript_result['segments']:
                    timestamp = int(segment['start'])
                    minutes = timestamp // 60
                    seconds = timestamp % 60
                    f.write(f"[{minutes:02d}:{seconds:02d}] {segment['text']}\n")
            
            # Prepare return data
            return {
                'video_id': video_id,
                'transcript': transcript_result,
                'analysis': analysis_results,
                'output_file': output_file,
                'success': True
            }
            
        except Exception as e:
            return {
                'error': f"Error saving analysis: {str(e)}",
                'success': False
            }

def main():
    """Main function for command line usage"""
    # Get API key from environment variable
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set")
        return

    # Initialize analyzer
    analyzer = YouTubeTranscriptAnalyzer(api_key)
    
    # Get YouTube URL from user
    url = input("Enter YouTube URL: ")
    
    # First get the transcript and save it
    video_id = analyzer.get_video_id(url)
    if not video_id:
        print("Error: Invalid YouTube URL")
        return
        
    transcript_result = analyzer.get_transcript(video_id)
    if 'error' in transcript_result:
        print("Error getting transcript:", transcript_result['error'])
        return
    
    # Generate timestamp for the file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    transcript_file = f"transcript_{timestamp}.txt"
    
    # Save transcript to file for review
    try:
        with open(transcript_file, 'w', encoding='utf-8') as f:
            f.write("YOUTUBE VIDEO TRANSCRIPT\n")
            f.write("=====================\n\n")
            f.write(f"Video URL: {url}\n")
            f.write(f"Transcript Language: {transcript_result['language']}\n\n")
            f.write("FULL TRANSCRIPT:\n")
            f.write("===============\n\n")
            f.write(transcript_result['text'])
            f.write("\n\nTIMESTAMPED SEGMENTS:\n")
            f.write("===================\n\n")
            for segment in transcript_result['segments']:
                timestamp = int(segment['start'])
                minutes = timestamp // 60
                seconds = timestamp % 60
                f.write(f"[{minutes:02d}:{seconds:02d}] {segment['text']}\n")
                
        print(f"\nTranscript has been saved to: {transcript_file}")
        print("Please review the transcript file and then proceed with word analysis.")
        
        # Wait for user to review the file
        input("\nPress Enter when you're ready to analyze specific words...")
        
        # Get words to analyze
        words_input = input("Enter words to analyze (comma-separated): ")
        words_to_analyze = [word.strip() for word in words_input.split(',')]
        
        # Process video and analyze words
        result = analyzer.process_video_with_analysis(url, words_to_analyze)
        
        if result.get('success', False):
            print(f"\nAnalysis complete! Results saved to: {result['output_file']}")
            print("\nAnalysis summary:")
            for word, analysis in result['analysis'].items():
                print(f"\nWord: {word}")
                if analysis['success']:
                    print(analysis['analysis'])
                else:
                    print(f"Error: {analysis['error']}")
        else:
            print("Error:", result.get('error', 'Unknown error occurred'))
            
    except Exception as e:
        print(f"Error saving transcript: {str(e)}")

if __name__ == "__main__":
    main()