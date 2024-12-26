from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from datetime import datetime
import tweepy

load_dotenv()

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# Update Twitter client initialization
twitter_client = tweepy.Client(
    consumer_key=os.getenv("TWITTER_API_KEY"),
    consumer_secret=os.getenv("TWITTER_API_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
)

class ProfileUpdate(BaseModel):
    username: str | None = None
    bio: str | None = None
    website: str | None = None
    location: str | None = None

class TweetCreate(BaseModel):
    content: str

@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    try:
        response = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        return response.data
    except Exception as e:
        print(f"Error fetching profile: {str(e)}")  # Debug log
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.patch("/api/profile/{user_id}")
async def update_profile(user_id: str, profile: ProfileUpdate):
    try:
        response = supabase.table("profiles").update(profile.dict(exclude_none=True)).eq("id", user_id).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/tweet/{user_id}")
async def create_tweet(user_id: str, tweet: TweetCreate):
    try:
        profile = supabase.table("profiles").select("twitter_post_count").eq("id", user_id).single().execute()
        current_count = profile.data.get("twitter_post_count", 0)

        if current_count >= 500:
            raise HTTPException(status_code=429, detail="Monthly tweet limit reached")

        twitter_response = twitter_client.create_tweet(text=tweet.content)
        tweet_id = twitter_response.data['id']

        response = supabase.table("profiles").update({
            "twitter_post_count": current_count + 1,
            "last_tweet_at": datetime.utcnow().isoformat(),
            "last_tweet_id": tweet_id
        }).eq("id", user_id).execute()

        return {
            "success": True,
            "new_count": current_count + 1,
            "tweet_id": tweet_id,
            "tweet_url": f"https://twitter.com/i/web/status/{tweet_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Add a new endpoint to get user's recent tweets
@app.get("/api/tweets/{user_id}")
async def get_tweets(user_id: str, limit: int = 10):
    try:
        # First get the profile to get Twitter username
        profile_response = supabase.table("profiles").select("twitter_username").eq("id", user_id).single().execute()
        
        if not profile_response.data:
            print(f"No profile found for user {user_id}")  # Debug log
            return {"tweets": []}
            
        username = profile_response.data.get("twitter_username")
        if not username:
            print(f"No Twitter username found for user {user_id}")  # Debug log
            return {"tweets": []}
        
        # Get user ID from username
        try:
            user = twitter_client.get_user(username=username)
            if not user or not user.data:
                print(f"No Twitter user found for username {username}")  # Debug log
                return {"tweets": []}
                
            # Get tweets
            tweets = twitter_client.get_users_tweets(
                id=user.data.id,
                max_results=limit,
                tweet_fields=['created_at', 'public_metrics']
            )
            
            if not tweets or not tweets.data:
                print(f"No tweets found for user {username}")  # Debug log
                return {"tweets": []}
            
            return {
                "tweets": [
                    {
                        "id": tweet.id,
                        "text": tweet.text,
                        "created_at": tweet.created_at,
                        "likes": tweet.public_metrics['like_count'],
                        "retweets": tweet.public_metrics['retweet_count'],
                        "url": f"https://twitter.com/i/web/status/{tweet.id}"
                    }
                    for tweet in tweets.data
                ]
            }
        except Exception as e:
            print(f"Twitter API error: {str(e)}")  # Debug log
            return {"tweets": [], "error": str(e)}
            
    except Exception as e:
        print(f"General error in get_tweets: {str(e)}")  # Debug log
        raise HTTPException(status_code=500, detail=str(e)) 