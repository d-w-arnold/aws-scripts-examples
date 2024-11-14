#!/bin/bash

# Check if version type is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <major|minor|patch>"
  exit 1
fi

# Get the directory path of the (react-native) git repo
if [ -z "${REACT_NATIVE_DIR}" ]; then
  echo "REACT_NATIVE_DIR is not set"
  echo 'Set before running the script:'
  echo 'export REACT_NATIVE_DIR="/Users/<username>/dev/cat-mobile"'
  exit 2
else
  echo "REACT_NATIVE_DIR is set to: ${REACT_NATIVE_DIR}"
fi

# Check if the path is a directory
if [ -d "${REACT_NATIVE_DIR}" ]; then
    # shellcheck disable=SC2164
    cd "${REACT_NATIVE_DIR}"
else
    echo "${REACT_NATIVE_DIR} is not a directory"
    exit 3
fi

# Get the global Git user email
GIT_EMAIL=$(git config --global user.email)

# Check if the email is set
if [ -z "${GIT_EMAIL}" ]; then
  echo "Global Git user email is not set."
else
  echo "Global Git user email: ${GIT_EMAIL}"
fi

# Get the script name
SCRIPT_NAME=$(basename "$0")

# Create a pull request on Bitbucket
# Adjust the following variables as necessary
BITBUCKET_USERNAME="atlassian_foobar"
BITBUCKET_REPO="${REACT_NATIVE_DIR##*/}"
BITBUCKET_WORKSPACE="foobar-products-development"

REGION="eu-west-2"
BITBUCKET_APP_PASSWORD="arn:aws:secretsmanager:${REGION}:123456789123:secret:bitbucket/atlassian/app-password/react-native-dev-to-main-pre-merge-J30X5N"
echo "## Load from AWS Secrets Manager, the Bitbucket App Password: '${BITBUCKET_APP_PASSWORD}'"
BITBUCKET_APP_PASSWORD_SECRET=$(aws secretsmanager get-secret-value --region "${REGION}" --secret-id "${BITBUCKET_APP_PASSWORD}" --query "SecretString" --output text)

VERSION_TYPE=$1
CAPITALIZED_VERSION_TYPE=$(python3 -c "print('${VERSION_TYPE}'.capitalize())")

SOURCE_BRANCH_NAME="dev"
DEST_BRANCH_NAME="main"
git checkout "${SOURCE_BRANCH_NAME}"
git pull

PACKAGE_FILE="package.json"

# Read the current version from package.json
CURRENT_VERSION=$(jq -r '.version' "${PACKAGE_FILE}")
echo "The current version: ${CURRENT_VERSION}"

if [[ -z "${CURRENT_VERSION}" ]]; then
  echo "Failed to read version from ${PACKAGE_FILE}"
  exit 4
fi

# Split the current version into major, minor, and patch
IFS='.' read -r MAJOR MINOR PATCH <<< "${CURRENT_VERSION}"

case $VERSION_TYPE in
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
  patch)
    PATCH=$((PATCH + 1))
    ;;
  *)
    echo "Invalid version type. Use 'major', 'minor', or 'patch'."
    exit 5
    ;;
esac

# Create the new version string
NEW_VERSION="$MAJOR.$MINOR.$PATCH"
echo "The new version: ${NEW_VERSION}"

# Update the version in package.json
if jq --arg ver "${NEW_VERSION}" '.version = $ver' "${PACKAGE_FILE}" > tmp.$$.json && mv tmp.$$.json "${PACKAGE_FILE}"; then
  echo "Updated version to '${NEW_VERSION}' in ${PACKAGE_FILE}"
else
  echo "Failed to update version in ${PACKAGE_FILE}"
  exit 6
fi

# Git commit changes
git add "${PACKAGE_FILE}"
git commit -m "Bump version to ${NEW_VERSION}"

# Push changes to the repository
git push origin HEAD

# Fetch default reviewers
REVIEWERS="$(curl -s -X GET "https://api.bitbucket.org/2.0/repositories/${BITBUCKET_WORKSPACE}/${BITBUCKET_REPO}/default-reviewers" \
-u "${BITBUCKET_USERNAME}:${BITBUCKET_APP_PASSWORD_SECRET}" | jq '[.values[] | {uuid: .uuid}]' | sed 's/[[:space:]]//g') "

# Create data for POST request
DATA='{
  "title": "['"${CAPITALIZED_VERSION_TYPE}"'] Bump version to '"${NEW_VERSION}"'",
  "source": {
    "branch": {
      "name": "'"${SOURCE_BRANCH_NAME}"'"
    }
  },
  "destination": {
    "branch": {
      "name":  "'"${DEST_BRANCH_NAME}"'"
    }
  },
  "description": "PR created by user: '"${GIT_EMAIL}"' (using: '"${SCRIPT_NAME}"')",
  "reviewers": null,
  "close_source_branch": false
}'
DATA="$(echo "${DATA}" | python3 -c "import json,sys;obj=json.load(sys.stdin);obj['reviewers']=${REVIEWERS};print(json.dumps(obj))")"

# Create the pull request
echo "Creating pull request ..."
PR_RESPONSE=$(curl -s -X POST "https://api.bitbucket.org/2.0/repositories/${BITBUCKET_WORKSPACE}/${BITBUCKET_REPO}/pullrequests" \
  -H "Content-Type: application/json" \
  -u "${BITBUCKET_USERNAME}:${BITBUCKET_APP_PASSWORD_SECRET}" \
  -d "${DATA}")

# Extract the pull request ID from the response
PR_ID=$(echo "$PR_RESPONSE" | jq -r '.id')

# Check if the pull request was created successfully
if [ -z "${PR_ID}" ]; then
  echo "Failed to create pull request: $PR_RESPONSE"
  exit 7
fi

echo "Pull request created successfully with ID: ${PR_ID} (for version: ${NEW_VERSION})"
