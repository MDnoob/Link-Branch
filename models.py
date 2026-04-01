from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id               = Column(Integer, primary_key=True, index=True)
    username         = Column(String(50), unique=True, nullable=False, index=True)
    email            = Column(String(120), unique=True, nullable=False)
    phone            = Column(String(25), nullable=True, index=True)
    hashed_password  = Column(String(255), nullable=False)

    # Profile
    display_name     = Column(String(100), nullable=True)
    bio              = Column(Text, nullable=True)
    avatar_url       = Column(String(500), nullable=True)
    avatar_shape     = Column(String(20), default='circle')
    avatar_size      = Column(String(20), default='medium')
    avatar_fit       = Column(String(20), default='cover')
    avatar_scale     = Column(Integer, default=100)

    # Background
    bg_type          = Column(String(20), default='solid')
    bg_color         = Column(String(20), default='#f7f6f2')
    bg_gradient      = Column(String(100), nullable=True)
    bg_image         = Column(String(500), nullable=True)
    bg_overlay       = Column(Integer, default=0)

    # Island card
    island_style     = Column(String(20), default='glass')   # glass | solid | image
    island_color     = Column(String(20), default='#ffffff')
    island_gradient  = Column(String(120), nullable=True)
    island_image     = Column(String(500), nullable=True)
    island_overlay   = Column(Integer, default=18)

    # Buttons
    btn_style        = Column(String(20), default='pill')
    btn_fill         = Column(String(20), default='filled')
    btn_color        = Column(String(20), default='#1a1a18')
    btn_text_color   = Column(String(20), default='#ffffff')
    btn_hover        = Column(String(20), default='lift')

    # Typography & text colors
    font_family      = Column(String(50), default='Inter')
    font_size        = Column(String(20), default='medium')
    text_name_color  = Column(String(20), default='#1a1a18')
    text_bio_color   = Column(String(20), default='#555555')

    # Misc
    show_branding    = Column(Boolean, default=True)
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    links          = relationship("Link",        back_populates="owner", cascade="all, delete-orphan")
    assets         = relationship("Asset",       back_populates="owner", cascade="all, delete-orphan")
    redirect_links = relationship("RedirectLink", back_populates="owner", cascade="all, delete-orphan")
    profile_views  = relationship("ProfileView", back_populates="owner", cascade="all, delete-orphan")
    link_clicks    = relationship("LinkClick",   back_populates="owner", cascade="all, delete-orphan")
    share_events   = relationship("ShareEvent",  back_populates="owner", cascade="all, delete-orphan")


class Link(Base):
    __tablename__ = "links"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    title       = Column(String(200), nullable=False)
    url         = Column(String(500), nullable=True)    # nullable — sections have no URL
    icon        = Column(String(255), nullable=True)
    is_active   = Column(Boolean, default=True)
    is_section  = Column(Boolean, default=False)       # ← NEW: True = text divider, not a link
    sort_order  = Column(Integer, default=0)
    created_at  = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="links")


class Asset(Base):
    __tablename__ = "assets"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename   = Column(String(255), nullable=False)
    label      = Column(String(100), nullable=True)
    url        = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="assets")


class RedirectLink(Base):
    __tablename__ = "redirect_links"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title      = Column(String(200), nullable=False)
    url        = Column(String(500), nullable=False)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    owner = relationship("User", back_populates="redirect_links")


class ProfileView(Base):
    __tablename__ = "profile_views"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    path       = Column(String(255), nullable=True)
    viewer_ip  = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    referer    = Column(String(500), nullable=True)
    referrer_domain = Column(String(255), nullable=True, index=True)
    device_type = Column(String(20), nullable=True, index=True)
    country    = Column(String(100), nullable=True, index=True)
    city       = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    owner = relationship("User", back_populates="profile_views")


class LinkClick(Base):
    __tablename__ = "link_clicks"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    link_id         = Column(Integer, nullable=True, index=True)
    destination_url = Column(String(500), nullable=True)
    ref             = Column(String(100), nullable=True)
    viewer_ip       = Column(String(64), nullable=True)
    user_agent      = Column(String(255), nullable=True)
    referer         = Column(String(500), nullable=True)
    referrer_domain = Column(String(255), nullable=True, index=True)
    device_type     = Column(String(20), nullable=True, index=True)
    country         = Column(String(100), nullable=True, index=True)
    city            = Column(String(100), nullable=True, index=True)
    click_source    = Column(String(40), nullable=True, index=True)
    created_at      = Column(DateTime, default=datetime.utcnow, index=True)

    owner = relationship("User", back_populates="link_clicks")


class ShareEvent(Base):
    __tablename__ = "share_events"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    link_id    = Column(Integer, nullable=True, index=True)
    platform   = Column(String(50), nullable=True)
    path       = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    owner = relationship("User", back_populates="share_events")
