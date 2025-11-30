# Claude Code Development Notes

## Git Push Note

When pushing to the GitHub repository, use `--no-verify` flag to bypass Code Defender:

```bash
git push --no-verify
```

## Project Overview

This is a video highlight extraction system that uses Amazon Nova and Google Gemini AI models for intelligent video analysis.

### Current Features

1. **Embedding-based Mode**: Uses vector embeddings to match highlight segments
2. **Direct Localization Mode**: AI directly identifies timestamp-based highlights with parallel processing
3. **Parallel AI Processing**:
   - Simultaneously runs Amazon Nova Pro, Gemini 2.5 Flash, and Gemini 2.5 Pro
   - Users can compare results side-by-side
   - Select best AI result with editable criteria
4. **Three-stage AI Processing**:
   - Generate criteria/standards (parallel)
   - User selects preferred AI result
   - Analyze video content
   - Extract and stitch highlights

### Latest Updates (Nov 30, 2024)

✅ **Parallel AI Processing**: Run Nova Pro, Gemini 2.5 Flash, and Gemini 2.5 Pro simultaneously
✅ **Horizontal UI Layout**: Display all 3 AI results side-by-side in cards
✅ **Model Selection**: Allow users to select between AI results with editable prompts
✅ **Gemini Integration**: Added support for Gemini 2.5 Flash and Gemini 2.5 Pro models

## Architecture

- **Backend**: Flask (Python)
- **Frontend**: Vanilla JavaScript
- **AI Models**:
  - Amazon Nova Pro (current)
  - Google Gemini 2.5 / 2.5 Pro (planned)
- **Video Processing**: FFmpeg
- **Storage**: AWS S3

## Setup Instructions

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Configure environment variables**:
Copy `.env.example` to `.env` and fill in your API keys:
```bash
cp .env.example .env
```

Required API keys:
- AWS credentials (for Amazon Nova and S3)
- Google Gemini API key (for Gemini 2.5 models)

3. **Run the application**:
```bash
python app.py
```

The app will be available at `http://localhost:5000`

## Development Commands

```bash
# Run the application
python app.py

# Commit changes
git add .
git commit -m "your message"
git push --no-verify
```

## API Endpoints

### Highlight Extraction
- `POST /api/extract-direct` - Start direct mode extraction (parallel AI analysis)
- `POST /api/direct-select-model/<job_id>` - Select AI model result
- `POST /api/direct-confirm-highlights/<job_id>` - Confirm highlight timestamps
- `GET /api/job-status/<job_id>` - Get job status and results
- `GET /api/download-highlight/<job_id>` - Download final highlight video

### Legacy Endpoints
- `POST /api/extract-highlight` - Embedding-based extraction
- `POST /api/direct-confirm-summary/<job_id>` - Legacy confirmation (single model)
