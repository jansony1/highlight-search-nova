# Video Highlight Extractor with Amazon Nova

An intelligent video highlight extraction system powered by Amazon Nova AI models. This application automatically analyzes videos, identifies key moments based on user-defined themes, and generates highlight reels with smooth transitions.

## Features

### 🎬 Intelligent Video Analysis
- **AI-Powered Criteria Generation**: Uses Claude Opus 4.5 to generate custom highlight criteria based on user themes
- **Smart Video Understanding**: Leverages Amazon Nova Pro for comprehensive video content analysis
- **Multi-modal Embeddings**: Utilizes Amazon Nova MME for semantic video-text matching

### 🎯 Advanced Highlight Detection
- **Semantic Matching**: Top-K selection strategy for finding the best highlight moments
- **Automatic Deduplication**: Intelligent filtering to remove duplicate and overlapping clips
- **Configurable Thresholds**: Adjustable similarity thresholds and clip selection parameters

### 🎨 Professional Video Production
- **Smooth Transitions**: Crossfade video and audio transitions between clips
- **Quality Preservation**: Maintains original video resolution and quality
- **Smart Compression**: Intelligent compression strategy based on video size
- **Fast Processing**: Optimized lazy extraction - only processes selected clips

### 💡 User-Friendly Interface
- **Interactive Web UI**: Clean, modern interface built with Flask
- **Real-time Progress**: Live updates on processing status with detailed step information
- **Manual Editing**: Review and edit AI-generated criteria and analysis before processing
- **Preview & Download**: Preview generated highlights and download final videos

## Architecture

### Core Components

1. **Criteria Generation** (Claude Opus 4.5)
   - Analyzes user theme
   - Generates customized highlight detection criteria

2. **Video Compression** (FFmpeg)
   - 3-tier compression strategy
   - ≤25MB: No compression
   - 25-100MB: Skip compression (avoid quality loss)
   - >100MB: Compress to 100MB target

3. **Video Analysis** (Amazon Nova Pro)
   - Inline analysis for videos <25MB
   - S3 URI analysis for videos ≥25MB (up to 1GB)
   - Extracts key moments and storylines

4. **Embedding Generation** (Amazon Nova MME)
   - Segmented embeddings (3-second intervals)
   - Async API for large videos
   - Audio-video combined embeddings

5. **Semantic Matching**
   - Top-K selection per highlight point
   - Cosine similarity scoring
   - Dual-stage deduplication

6. **Video Stitching** (FFmpeg)
   - Crossfade transitions (0.5s default)
   - Audio fade in/out
   - Professional output quality

## Technology Stack

- **Backend**: Python 3.11, Flask
- **AI Models**:
  - Claude Opus 4.5 (Criteria Generation)
  - Amazon Nova Pro (Video Analysis)
  - Amazon Nova MME (Embeddings)
- **Video Processing**: FFmpeg
- **Cloud Services**: AWS S3, Amazon Bedrock
- **Frontend**: HTML5, CSS3, JavaScript

## Prerequisites

- Python 3.11+
- FFmpeg installed
- AWS Account with Bedrock access
- Amazon Nova models enabled in your region

## Installation

1. Clone the repository:
```bash
git clone https://github.com/jansony1/highlight-search-nova.git
cd highlight-search-nova
```

2. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install FFmpeg:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

5. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your AWS credentials and settings
```

## Configuration

Create a `.env` file with the following variables:

```env
# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# S3 Configuration
S3_BUCKET=your-bucket-name

# Flask Configuration
SECRET_KEY=your-secret-key
```

## Usage

1. Start the application:
```bash
python app.py
```

2. Open your browser and navigate to:
```
http://localhost:5000
```

3. Navigate to the Highlight Extractor:
```
http://localhost:5000/highlight
```

4. Follow the workflow:
   - **Step 1**: Enter your highlight theme (e.g., "exciting outdoor adventures")
   - **Step 2**: Upload your video (up to 500MB)
   - **Step 3**: Click "Start Processing"
   - **Step 4**: Review and confirm AI-generated criteria
   - **Step 5**: Review and confirm video analysis
   - **Step 6**: Wait for processing to complete
   - **Step 7**: Download your highlight video!

## Processing Pipeline

```
User Input (Theme + Video)
    ↓
[1] Generate Criteria (Claude Opus 4.5)
    ↓
[2] Compress Video (FFmpeg - Smart Strategy)
    ↓
[3] Analyze Video (Nova Pro - Extract Key Moments)
    ↓
[4] Generate Embeddings (Nova MME - 3s segments)
    ↓
[5] Match Clips (Top-K Semantic Matching)
    ↓
[6] Stitch Video (FFmpeg - Smooth Transitions)
    ↓
Final Highlight Video
```

## Performance Optimization

### Lazy Extraction
- Generates embeddings for all segments (~196 for 10min video)
- Only extracts actual video clips for matched segments (5-20 clips)
- **10-20x faster** than extracting all clips upfront

### Smart Compression
- Avoids unnecessary re-encoding
- Preserves original quality when possible
- Only compresses when needed for API limits

### Async Processing
- Background threading for long operations
- Real-time progress updates
- Non-blocking user interface

## API Endpoints

### Highlight Extraction
- `POST /api/extract-highlight` - Start highlight extraction
- `GET /api/job-status/<job_id>` - Get processing status
- `GET /api/download-highlight/<job_id>` - Download final video
- `POST /api/confirm-criteria/<job_id>` - Confirm edited criteria
- `POST /api/confirm-analysis/<job_id>` - Confirm edited analysis

## Configuration Parameters

### Matching Parameters (in `highlight_extractor.py`)

```python
# Similarity threshold (lower = more clips)
threshold = 0.05  # Range: 0.01-0.15

# Clips per highlight point
top_k_per_point = 3  # Range: 1-5

# Segment duration
segment_duration = 3  # seconds

# Transition duration
transition_duration = 0.5  # seconds
```

## Troubleshooting

### Common Issues

1. **"Model identifier is invalid"**
   - Ensure you're using the correct model ID for your region
   - Check if Nova models are enabled in your AWS account

2. **"Read timeout on endpoint URL"**
   - Large videos may take time to process
   - System automatically retries with exponential backoff

3. **"Video compression makes file larger"**
   - Fixed in latest version
   - 25-100MB videos now skip compression

4. **"Too few clips selected"**
   - Adjust `threshold` parameter (lower = more clips)
   - Increase `top_k_per_point` (more clips per highlight point)

## Project Structure

```
.
├── app.py                      # Flask application
├── config.py                   # Configuration
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (create from .env.example)
├── utils/
│   ├── highlight_extractor.py # Core highlight extraction logic
│   ├── s3_handler.py          # S3 operations
│   ├── embedding.py           # Sync embedding generation
│   └── async_embedding.py     # Async embedding generation
├── templates/
│   ├── index.html             # Homepage
│   └── highlight.html         # Highlight extractor interface
└── static/
    ├── css/                   # Stylesheets
    ├── js/                    # JavaScript files
    ├── uploads/               # Temporary uploads
    ├── clips/                 # Generated clips
    └── highlights/            # Final highlight videos
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Amazon Bedrock team for Nova models
- FFmpeg community for video processing tools
- Flask community for the web framework

## Contact

For questions or support, please open an issue on GitHub.

---

Built with ❤️ using Amazon Nova AI
