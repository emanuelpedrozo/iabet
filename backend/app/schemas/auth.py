from pydantic import BaseModel, EmailStr, Field
class LoginRequest(BaseModel): email: EmailStr; password: str = Field(min_length=8)
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    invite_code: str | None = Field(default=None, max_length=200)
class TokenResponse(BaseModel): access_token: str; token_type: str="bearer"; role: str
