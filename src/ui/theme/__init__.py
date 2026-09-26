from .palettes import DARK_PALETTE, LIGHT_PALETTE
from .stylesheet import build_stylesheet
from .tokens import ThemeTokens


class ModernTheme:
    FONT_FAMILY = ThemeTokens.FONT_FAMILY
    FONT_SIZE_XS = ThemeTokens.FONT_SIZE_XS
    FONT_SIZE_SM = ThemeTokens.FONT_SIZE_SM
    FONT_SIZE_BASE = ThemeTokens.FONT_SIZE_BASE
    FONT_SIZE_MD = ThemeTokens.FONT_SIZE_MD
    FONT_SIZE_LG = ThemeTokens.FONT_SIZE_LG
    FONT_SIZE_XL = ThemeTokens.FONT_SIZE_XL
    FONT_SIZE_2XL = ThemeTokens.FONT_SIZE_2XL

    RADIUS_SM = ThemeTokens.RADIUS_SM
    RADIUS_MD = ThemeTokens.RADIUS_MD
    RADIUS_LG = ThemeTokens.RADIUS_LG
    RADIUS_XL = ThemeTokens.RADIUS_XL
    RADIUS_PILL = ThemeTokens.RADIUS_PILL

    LIGHT_PALETTE = LIGHT_PALETTE
    DARK_PALETTE = DARK_PALETTE

    @staticmethod
    def get_palette(mode="light"):
        return DARK_PALETTE if mode == "dark" else LIGHT_PALETTE

    @staticmethod
    def get_stylesheet(mode="light", density="comfortable"):
        return build_stylesheet(mode, density=density)


__all__ = ["ModernTheme"]
