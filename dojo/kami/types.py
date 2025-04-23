from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class ServeAxonPayload(BaseModel):
    netuid: int
    version: int = 1
    ip: int
    port: int
    ipType: int
    protocol: int
    placeholder1: int = 0
    placeholder2: int = 0


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
    ip: int
    port: int
    ipType: int
    protocol: int
    placeholder1: int
    placeholder2: int


class SubnetMetagraph(BaseModel):
    netuid: int
    name: List[int]
    symbol: List[int]
    identity: SubnetIdentity
    networkRegisteredAt: int
    ownerHotkey: str
    ownerColdkey: str
    block: int
    tempo: int
    lastStep: int
    blocksSinceLastStep: int
    subnetEmission: int
    alphaIn: int
    alphaOut: int
    taoIn: int
    alphaOutEmission: int
    alphaInEmission: int
    taoInEmission: int
    pendingAlphaEmission: int
    pendingRootEmission: int
    subnetVolume: int
    movingPrice: MovingPrice
    rho: int
    kappa: int
    minAllowedWeights: int
    maxAllowedWeights: int
    weightsVersion: int
    weightsRateLimit: int
    activityCutoff: int
    maxValidators: int
    numUids: int
    maxUids: int
    burn: int
    difficulty: int
    registrationAllowed: bool
    powRegistrationAllowed: bool
    immunityPeriod: int
    minDifficulty: int
    maxDifficulty: str
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
    identities: List[IdentitiesInfo]
    axons: List[AxonInfo]
    active: List[bool]
    validatorPermit: List[bool]
    pruningScore: List[int]
    lastUpdate: List[int]
    emission: List[int]
    dividends: List[int]
    incentives: List[int]
    consensus: List[int]
    trust: List[int]
    rank: List[int]
    blockAtRegistration: List[int]
    alphaStake: List[int]
    taoStake: List[int]
    totalStake: List[int]
    taoDividendsPerHotkey: List[Tuple[str, int]]
    alphaDividendsPerHotkey: List[Tuple[str, int]]
