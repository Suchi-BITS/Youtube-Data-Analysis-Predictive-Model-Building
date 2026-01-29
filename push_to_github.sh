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

echo "Fetching from remote repository..."
git fetch origin

# Check if remote has any branches
if git branch -r | grep -q "origin/"; then
  echo "Remote repository has existing branches."
  
  # If there's a main branch on remote, pull it first
  if git branch -r | grep -q "origin/main"; then
    echo "Pulling from origin/main..."
    git pull origin main --allow-unrelated-histories || echo "Could not pull automatically. Continuing anyway."
  # If there's a master branch on remote, pull it first  
  elif git branch -r | grep -q "origin/master"; then
    echo "Pulling from origin/master..."
    git pull origin master --allow-unrelated-histories || echo "Could not pull automatically. Continuing anyway."
  fi
fi

echo "Adding all files to Git..."
git add .

echo "Committing files..."
git commit -m "AWS ETL Pipeline for YouTube Analytics" || echo "No changes to commit"

echo "Pushing to GitHub..."
git push -u origin main || git push -u origin master

echo "Done! Your code has been pushed to GitHub." 