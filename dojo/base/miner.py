import asyncio
import traceback

from bittensor.utils.btlogging import logging as logger

from commons.utils import serve_axon
from dojo.base.neuron import BaseNeuron


class BaseMinerNeuron(BaseNeuron):
    """
    Base class for Bittensor miners.
    """

    def __init__(self):
        super().__init__()

    async def run(self):
        """
        Initiates and manages the main loop for the miner on the Bittensor network. The main loop handles graceful shutdown on keyboard interrupts and logs unforeseen errors.

        This function performs the following primary tasks:
        1. Check for registration on the Bittensor network.
        2. Starts the miner's axon, making it active on the network.
        3. Periodically resynchronizes with the chain; updating the metagraph with the latest network state and setting weights.

        The miner continues its operations until `should_exit` is set to True or an external interruption occurs.
        During each epoch of its operation, the miner waits for new blocks on the Bittensor network, updates its
        knowledge of the network (metagraph), and sets its weights. This process ensures the miner remains active
        and up-to-date with the network's latest state.

        Note:
            - The function leverages the global configurations set during the initialization of the miner.
            - The miner's axon serves as its interface to the Bittensor network, handling incoming and outgoing requests.

        Raises:
            KeyboardInterrupt: If the miner is stopped by a manual interruption.
            Exception: For unforeseen errors during the miner's operation, which are logged for diagnosis.
        """

        # manually always register and always sync metagraph when application starts
        self.resync_metagraph()
        self.sync()

        # Serve passes the axon information to the network + netuid we are hosting on.
        # This will auto-update if the axon port of external ip have changed.
        logger.info(f"Serving miner axon {self.axon} with netuid: {self.config.netuid}")
        serve_success = serve_axon(self.subtensor, self.axon, self.config)
        if serve_success:
            logger.success("Successfully served axon for miner!")
        else:
            logger.error("Failed to serve axon for miner, exiting.")
            exit()

        # Start  starts the miner's axon, making it active on the network.
        self.axon.start()

        logger.info(f"Miner starting at block: {str(self.block)}")

        # This loop maintains the miner's operations until intentionally stopped.
        try:
            while True:
                # Check if we should exit.
                if self.should_exit:
                    break

                # Sync metagraph and potentially set weights.
                self.sync()
                self.step += 1
                await asyncio.sleep(12)

        # If someone intentionally stops the miner, it'll safely terminate operations.
        except KeyboardInterrupt:
            self.axon.stop()
            logger.success("Miner killed by keyboard interrupt.")
            exit()

        # In case of unforeseen errors, the miner will log the error and continue operations.
        except Exception:
            logger.error(traceback.format_exc())

    def set_weights(self):
        pass

    def resync_metagraph(self):
        """Resyncs the metagraph and updates the hotkeys and moving averages based on the new metagraph."""
        logger.info("resync_metagraph()")

        # Sync the metagraph.
        self.metagraph.sync(subtensor=self.subtensor)
