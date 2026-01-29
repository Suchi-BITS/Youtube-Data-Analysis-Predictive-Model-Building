#!/bin/bash

# Exit on error
set -e

echo "Initializing Git repository (if not already initialized)..."
if [ ! -d .git ]; then
  git init
  echo "Git repository initialized."
else
  echo "Git repository already exists."
fi

echo "Setting up remote origin..."
git remote remove origin 2>/dev/null || echo "No remote origin to remove"
git remote add origin https://github.com/AnuAlli/Build-An-Aws-ETL-Data-Pipeline-in-Python-on-Youtube-Data.git

echo "Adding all files to Git..."
git add .

echo "Committing files..."
git commit -m "AWS ETL Pipeline for YouTube Analytics" || echo "No changes to commit"

echo "Force pushing to GitHub..."
git push -f origin main

echo "Done! Your code has been pushed to GitHub." 