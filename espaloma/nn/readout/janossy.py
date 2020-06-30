# =============================================================================
# IMPORTS
# =============================================================================
import torch
import espaloma as esp
import dgl

# =============================================================================
# MODULE FUNCTIONS
# =============================================================================
class JanossyPooling(torch.nn.Module):
    """ Janossy pooling (arXiv:1811.01900) to average node representation
    for higher-order nodes.


    """

    def __init__(
        self,
        config,
        in_features,
        out_features=[2, 2, 2],
        levels=[2, 3, 4],
        pool=torch.add,
    ):
        super(JanossyPooling, self).__init__()
        # bookkeeping
        self.levels = levels
        self.pool = pool

        # set up networks
        for idx_level, level in enumerate(self.levels):

            # set up individual sequential networks
            setattr(
                self,
                "sequential_%s" % level,
                esp.nn.sequential._Sequential(
                    in_features=in_features * level,
                    config=config,
                    layer=torch.nn.Linear,
                ),
            )

            # get output features
            mid_features = [x for x in config if isinstance(x, int)][-1]

            setattr(
                self,
                "f_out_%s" % level,
                torch.nn.Linear(mid_features, out_features[idx_level]),
            )

    def forward(self, g):
        """ Forward pass.

        Parameters
        ----------
        g : dgl.DGLHeteroGraph,
            input graph.
        """

        # copy
        g.multi_update_all(
            {
                "n1_as_%s_in_n%s"
                % (relationship_idx, big_idx): (
                    dgl.function.copy_src("h", "m%s" % relationship_idx),
                    dgl.function.mean(
                        "m%s" % relationship_idx, "h%s" % relationship_idx
                    ),
                )
                for big_idx in self.levels
                for relationship_idx in range(big_idx)
            },
            cross_reducer="sum",
        )

        # pool
        for big_idx in self.levels:

            g.apply_nodes(
                func=lambda nodes: {
                    "theta": getattr(self, "f_out_%s" % big_idx)(
                        getattr(self, "sequential_%s" % big_idx)(
                            g=None,
                            x=self.pool(
                                torch.cat(
                                    [
                                        nodes.data["h%s" % relationship_idx]
                                        for relationship_idx in range(big_idx)
                                    ],
                                    dim=1,
                                ),
                                torch.cat(
                                    [
                                        nodes.data["h%s" % relationship_idx]
                                        for relationship_idx in range(
                                            big_idx - 1, -1, -1
                                        )
                                    ],
                                    dim=1,
                                ),
                            ),
                        )
                    )
                },
                ntype="n%s" % big_idx,
            )

            g.apply_nodes(
                func=lambda nodes: {
                    "k": nodes.data["theta"][:, 0],
                    "eq": nodes.data["theta"][:, 1],
                },
                ntype="n%s" % big_idx,
            )

        return g
