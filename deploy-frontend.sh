#!/bin/bash
# Deployment script for frontend
# Run this from your project root directory

echo "Building frontend..."
cd frontend
npm run build
cd ..

echo "Build complete! Files are in frontend_dist/"
echo ""
echo "To deploy to server, run:"
echo "  scp -r frontend_dist/* user@your-server:/home/ubuntu/apps/good-bingo/arif_bingo/frontend_dist/"
echo ""
echo "Or if you're already on the server:"
echo "  The files are ready in frontend_dist/ directory"

