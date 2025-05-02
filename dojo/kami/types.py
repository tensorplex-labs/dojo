from typing import Any, List, Tuple

from pydantic import BaseModel, field_validator

from dojo.chain.types import HexString


class SubnetHyperparameters(BaseModel):
    rho: int
    kappa: int
    immunityPeriod: int
    minAllowedWeights: int
    maxWeightsLimit: int
    tempo: int
    minDifficulty: HexString
    maxDifficulty: HexString
    difficulty: HexString
    weightsVersion: int
    weightsRateLimit: int
    adjustmentInterval: int
    activityCutoff: int
    registrationAllowed: bool
    targetRegsPerInterval: int
    minBurn: int
    maxBurn: int
    bondsMovingAvg: int
    maxRegsPerBlock: int
    servingRateLimit: int
    maxValidators: int
    adjustmentAlpha: str
    commitRevealPeriod: int
    commitRevealWeightsEnabled: bool
    alphaHigh: int
    alphaLow: int
    liquidAlphaEnabled: bool

    @field_validator("difficulty", "minDifficulty", "maxDifficulty", mode="before")
    def validate_number(cls, v: Any) -> HexString:
        if isinstance(v, str):
            return HexString(v)
        return v

    class Config:
        arbitrary_types_allowed = True


class ServeAxonPayload(BaseModel):
    netuid: int
    version: int = 1
    ip: int
    port: int
    ipType: int
    protocol: int
    placeholder1: int = 0
    placeholder2: int = 0


class SetWeightsPayload(BaseModel):
    netuid: int
    dests: List[int]
    weights: List[int]  # Normalized weights
    version_key: int


class CommitRevealPayload(BaseModel):
    netuid: int
    commit: int | bytes
    reveal_round: int


class MovingPrice(BaseModel):
    bits: int


class SubnetIdentity(BaseModel):
    subnetName: str
    githubRepo: str
    subnetContact: str
    subnetUrl: str
    discord: str
    description: str
    additional: str


class IdentitiesInfo(BaseModel):
    name: str
    url: str
    githubRepo: str
    image: str
    discord: str
    description: str
    additional: str


class AxonInfo(BaseModel):
    block: int
    version: int
    ip: str
    port: int
    ipType: int
    protocol: int
    placeholder1: int
    placeholder2: int


class SubnetMetagraph(BaseModel):
    netuid: int
    name: str
    symbol: str
    identity: SubnetIdentity
    networkRegisteredAt: int
    ownerHotkey: str
    ownerColdkey: str
    block: int
    tempo: int
    lastStep: int
    blocksSinceLastStep: int
    subnetEmission: int
    alphaIn: float
    alphaOut: float
    taoIn: float
    alphaOutEmission: float
    alphaInEmission: float
    taoInEmission: float
    pendingAlphaEmission: float
    pendingRootEmission: float
    subnetVolume: float
    movingPrice: MovingPrice
    rho: int
    kappa: int
    # # TODO: not sure if this field is present
    # minAllowedWeights: int
    # # TODO: not sure if this field is present
    # maxAllowedWeights: int
    weightsVersion: int
    weightsRateLimit: int
    activityCutoff: int
    maxValidators: int
    numUids: int
    maxUids: int
    burn: int
    difficulty: HexString
    registrationAllowed: bool
    powRegistrationAllowed: bool
    immunityPeriod: int
    minDifficulty: HexString
    maxDifficulty: HexString
    minBurn: int
    maxBurn: int
    adjustmentAlpha: str
    adjustmentInterval: int
    targetRegsPerInterval: bool
    maxRegsPerBlock: int
    servingRateLimit: int
    commitRevealWeightsEnabled: bool
    commitRevealPeriod: int
    liquidAlphaEnabled: bool
    alphaHigh: int
    alphaLow: int
    bondsMovingAvg: int
    hotkeys: List[str]
    coldkeys: List[str]
    identities: List[IdentitiesInfo | None]
    axons: List[AxonInfo]
    active: List[bool]
    validatorPermit: List[bool]
    pruningScore: List[int]
    lastUpdate: List[int]
    emission: List[float]
    dividends: List[float]
    incentives: List[float]
    consensus: List[float]
    trust: List[float]
    rank: List[float]
    blockAtRegistration: List[int]
    alphaStake: List[float]
    taoStake: List[float]
    totalStake: List[float]
    taoDividendsPerHotkey: List[Tuple[str, float]]
    alphaDividendsPerHotkey: List[Tuple[str, float]]

    @field_validator("difficulty", "minDifficulty", "maxDifficulty", mode="before")
    def validate_number(cls, v: Any) -> HexString:
        if isinstance(v, str):
            return HexString(v)
        return v

    class Config:
        arbitrary_types_allowed = True
